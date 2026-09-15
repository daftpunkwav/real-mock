"""Company web-research tests for src/realmock/domains/interview/process/company_research.py.

Covers: catalog/custom detection, context blending, digest rendering, bounded
research loop (success / unusable / crash / empty), session digest lookup.
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from realmock.domains.interview.models import InterviewProcess, InterviewSession
from realmock.domains.interview.process import company_research as cr
from tests.fakes import FakeLLMClient


# ---- needs_company_research / blend_company_context -------------------------


def test_needs_company_research() -> None:
    assert cr.needs_company_research("") is False
    assert cr.needs_company_research("   ") is False
    assert cr.needs_company_research("bytedance") is False
    assert cr.needs_company_research("字节跳动") is True
    assert cr.needs_company_research("Acme Corp") is True


def test_blend_company_context() -> None:
    assert cr.blend_company_context("catalog", "") == "catalog"
    assert cr.blend_company_context("", "") == ""
    assert cr.blend_company_context("catalog", "  DIGEST  ") == "DIGEST"


# ---- render_digest -----------------------------------------------------------


def _research_payload() -> dict:
    return {
        "process": "Resume screening then onsite loops",
        "rounds": "3 rounds: 2 technical + 1 HR",
        "focus": "project deep dives with quantified impact",
        "notes": "values business thinking",
        "sources": ["https://example.com/a"],
        "confidence": "medium",
    }


def test_render_digest_ok() -> None:
    out = cr.render_digest(_research_payload())
    assert out is not None
    assert "Interview process: Resume screening then onsite loops" in out
    assert "Round structure: 3 rounds: 2 technical + 1 HR" in out
    assert "Focus & question style: project deep dives" in out
    assert "Sources: https://example.com/a" in out
    assert "Confidence: medium" in out


def test_render_digest_sources_capped_at_five() -> None:
    payload = _research_payload()
    payload["sources"] = [f"https://example.com/{i}" for i in range(8)]
    out = cr.render_digest(payload)
    assert out is not None
    assert out.count("https://example.com/") == 5


def test_render_digest_missing_fields_become_unknown() -> None:
    out = cr.render_digest({"process": "p", "confidence": ""})
    assert out is not None
    assert "Round structure: unknown" in out
    assert "Notes: unknown" in out
    assert "Confidence: unknown" in out
    assert "Sources:" not in out


def test_render_digest_rejects_empty_and_garbage() -> None:
    assert cr.render_digest(None) is None
    assert cr.render_digest("nope") is None
    assert cr.render_digest({}) is None
    assert cr.render_digest({"process": "unknown", "rounds": "", "focus": None}) is None


# ---- research_company_context ------------------------------------------------


@pytest.mark.asyncio
async def test_research_success() -> None:
    llm = FakeLLMClient(tokens=[json.dumps(_research_payload(), ensure_ascii=False)])
    out = await cr.research_company_context(
        llm, company="字节跳动", role="Backend", level="mid", ui_locale="zh-CN"
    )
    assert out is not None
    assert "3 rounds: 2 technical + 1 HR" in out
    # The researcher gets a system prompt (contract) and a user message.
    assert len(llm.stream_calls) == 1
    assert "TARGET COMPANY" in llm.stream_calls[0][0]["content"].upper()
    assert "Target company: 字节跳动" in llm.stream_calls[0][1]["content"]


@pytest.mark.asyncio
async def test_research_unusable_output_returns_none() -> None:
    llm = FakeLLMClient(tokens=["I could not find anything, sorry."])
    assert await cr.research_company_context(llm, company="Acme", role="R", level="L") is None


@pytest.mark.asyncio
async def test_research_llm_crash_returns_none() -> None:
    class _Boom:
        api_key = "k"

        async def chat_message_stream(self, *a, **k):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    assert await cr.research_company_context(_Boom(), company="Acme", role="R", level="L") is None


@pytest.mark.asyncio
async def test_research_empty_company_short_circuits() -> None:
    llm = FakeLLMClient()
    assert await cr.research_company_context(llm, company="  ", role="R", level="L") is None
    assert llm.stream_calls == []


# ---- load_session_company_research -------------------------------------------


def _session(**overrides) -> InterviewSession:
    base = {
        "profile_id": 1,
        "role": "Backend",
        "level": "Senior",
        "company": "Acme",
        "workflow_type": "technical",
        "status": "pending",
        "current_phase": "identity_check",
        "agent_state": "{}",
        "messages": "[]",
    }
    base.update(overrides)
    return InterviewSession(**base)


def test_load_session_research_standalone(db) -> None:
    s = _session(company_research="OWN")
    db.add(s)
    db.commit()
    assert cr.load_session_company_research(db, s) == "OWN"
    plain = _session()
    assert cr.load_session_company_research(db, plain) == ""


def test_load_session_research_prefers_own_over_process(db) -> None:
    proc = InterviewProcess(profile_id=1, role="R", level="L", company="Acme",
                            company_research="PROC")
    db.add(proc)
    db.commit()
    db.refresh(proc)
    s = _session(process_id=proc.id, round_no=1, company_research="OWN")
    db.add(s)
    db.commit()
    assert cr.load_session_company_research(db, s) == "OWN"


def test_load_session_research_falls_back_to_process(db) -> None:
    proc = InterviewProcess(profile_id=1, role="R", level="L", company="Acme",
                            company_research="PROC")
    db.add(proc)
    db.commit()
    db.refresh(proc)
    s = _session(process_id=proc.id, round_no=1)
    db.add(s)
    db.commit()
    assert cr.load_session_company_research(db, s) == "PROC"


def test_load_session_research_missing_process_row(db) -> None:
    s = _session(process_id=99999, round_no=1)
    assert cr.load_session_company_research(db, s) == ""


def test_load_session_research_tolerates_plain_rows() -> None:
    # Session-less rows (e.g. test doubles) degrade to empty without a db hit.
    assert cr.load_session_company_research(None, SimpleNamespace(company_research="")) == ""
    assert cr.load_session_company_research(None, SimpleNamespace()) == ""
