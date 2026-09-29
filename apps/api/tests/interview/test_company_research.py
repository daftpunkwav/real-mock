"""Company web-research tests for src/realmock/domains/interview/agents/research/company_research.py.

Covers: catalog/custom detection, context blending, digest rendering, bounded
research loop (success / unusable / crash / empty), session digest lookup.
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from realmock.domains.interview.models import InterviewProcess, InterviewSession
from realmock.domains.interview.agents.research import company_research as cr
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
    proc = InterviewProcess(
        profile_id=1, role="R", level="L", company="Acme", company_research="PROC"
    )
    db.add(proc)
    db.commit()
    db.refresh(proc)
    s = _session(process_id=proc.id, round_no=1, company_research="OWN")
    db.add(s)
    db.commit()
    assert cr.load_session_company_research(db, s) == "OWN"


def test_load_session_research_falls_back_to_process(db) -> None:
    proc = InterviewProcess(
        profile_id=1, role="R", level="L", company="Acme", company_research="PROC"
    )
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


# ---- P1: relaxed budgets + delayed retry ----


def test_research_budgets_relaxed_for_accuracy():
    from realmock.domains.interview.agents.research import company_research as mod

    assert mod.RESEARCH_MAX_ROUNDS == 10
    assert mod.RESEARCH_SEARCH_BUDGET == 6
    assert mod.RESEARCH_FETCH_BUDGET == 4
    assert mod.STANDALONE_SEARCH_BUDGET == 4
    assert mod.STANDALONE_FETCH_BUDGET == 3
    assert mod.PROCESS_MAX_SECONDS == 150.0
    assert mod.RESEARCH_TOOL_TIMEOUT_SECONDS == 25.0


def test_schedule_research_retry_persists_delayed_digest(monkeypatch):
    import asyncio

    from realmock.domains.interview.agents.research import company_research as mod

    persisted: list[str] = []
    calls = {"n": 0}

    async def _fake_research(llm, **kwargs):
        calls["n"] += 1
        return "Interview process: digest"

    monkeypatch.setattr(mod, "RETRY_DELAY_SECONDS", 0.01)
    monkeypatch.setattr(mod, "research_company_context", _fake_research)

    llm = object()

    async def _flow():
        assert (
            mod.schedule_research_retry(
                llm,
                company="Acme",
                role="dev",
                level="senior",
                ui_locale=None,
                search_budget=1,
                fetch_budget=1,
                max_seconds=1.0,
                persist=persisted.append,
            )
            is True
        )
        # A second schedule for the same company while one is pending is refused.
        assert (
            mod.schedule_research_retry(
                llm,
                company="acme ",
                role=None,
                level=None,
                ui_locale=None,
                search_budget=1,
                fetch_budget=1,
                max_seconds=1.0,
                persist=persisted.append,
            )
            is False
        )
        await asyncio.gather(*list(mod._RETRY_TASKS))

    asyncio.run(_flow())
    assert persisted == ["Interview process: digest"]
    assert calls["n"] == 1


# ---- cross-session digest cache ----------------------------------------------


def test_digest_cache_roundtrip(db) -> None:
    assert cr.get_cached_digest("Acme Corp", "Backend", "zh-CN") is None
    cr.store_digest_cache("Acme Corp", "Backend", "zh-CN", "Interview process: cached digest")
    assert (
        cr.get_cached_digest("Acme Corp", "Backend", "zh-CN") == "Interview process: cached digest"
    )
    # The key folds company + role + language: a different locale misses.
    assert cr.get_cached_digest("acme corp", "backend", "en") is None


def test_digest_cache_ignores_blank_inputs(db) -> None:
    cr.store_digest_cache("", "Backend", "en", "digest")
    cr.store_digest_cache("Acme", "Backend", "en", "   ")
    assert cr.get_cached_digest("", "Backend", "en") is None
    assert cr.get_cached_digest("Acme", "Backend", "en") is None


@pytest.mark.asyncio
async def test_cached_research_reads_cache_before_llm(db) -> None:
    cr.store_digest_cache("Acme Corp", "Backend", "en", "Interview process: from cache")
    llm = FakeLLMClient(tokens=["would-be research"])
    out = await cr.research_company_context_cached(
        llm, company="Acme Corp", role="Backend", level="mid"
    )
    assert out == "Interview process: from cache"
    # The research loop never ran: the whole point of the cache.
    assert llm.stream_calls == []


@pytest.mark.asyncio
async def test_cached_research_miss_runs_and_stores(db) -> None:
    llm = FakeLLMClient(tokens=[json.dumps(_research_payload(), ensure_ascii=False)])
    out = await cr.research_company_context_cached(
        llm, company="Acme Corp", role="Backend", level="mid"
    )
    assert out is not None
    assert cr.get_cached_digest("acmecorp", "Backend", "en") == out


@pytest.mark.asyncio
async def test_cached_research_failure_is_not_cached(db) -> None:
    llm = FakeLLMClient(tokens=["unusable output"])
    assert (
        await cr.research_company_context_cached(llm, company="Acme", role="R", level="L") is None
    )
    assert cr.get_cached_digest("Acme", "R", "en") is None
