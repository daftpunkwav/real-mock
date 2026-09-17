"""Plan planner tests for src/realmock/domains/interview/agents/planning/planner.py.

Covers: resume/config/dump/fallback/process-section/round-criteria/generate/wait/ensure plan
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from realmock.domains.interview.agents.planning import planner as pl
from realmock.domains.interview.process.plan_schema import InterviewPlan
from tests.fakes import FakeLLMClient


def _valid_plan_dict(n=8):
    return {
        "round_note": "Round 1",
        "source": "agent",
        "language": "zh",
        "opening": {"style": "identity_confirm", "note": ""},
        "steps": [
            {"title": f"Step {i}", "focus": f"focus {i}", "max_questions": 2}
            for i in range(n)
        ],
    }


def test_resume_summary() -> None:
    assert pl._resume_summary(None) is None
    assert pl._resume_summary("bad") is None
    out = pl._resume_summary({"skills": ["Py"], "projects": [{"a": 1}], "summary": "s"})
    assert out == {"skills": ["Py"], "projects": [{"a": 1}], "summary": "s"}


def test_config_shim_defaults() -> None:
    s = SimpleNamespace(
        role="R", level="L", company="C", workflow_type=None,
        personality=None, strictness=None, interview_style=None,
    )
    shim = pl._config_shim(s)
    assert shim.workflow_type == "technical"
    assert shim.personality == "professional"
    assert shim.strictness == 3
    assert shim.interview_style == "deep_dive"


def test_dump_and_fallback_plan() -> None:
    from realmock.domains.interview.workflows import get_workflow

    plan = pl.fallback_plan_for(SimpleNamespace(workflow_type="technical"))
    assert isinstance(plan, InterviewPlan)
    assert plan.source == "fallback"
    dumped = pl._dump_plan(plan)
    assert json.loads(dumped)["source"] == "fallback"
    wf = get_workflow("unknown-id")
    assert wf.id == "technical"


def test_process_section_no_process() -> None:
    s = SimpleNamespace(process_id=None)
    assert pl._process_section(SimpleNamespace(), s) == ""


def test_process_section_missing_row(db) -> None:
    from realmock.domains.interview.models import InterviewSession

    s = InterviewSession(
        profile_id=1, role="R", level="L", company="C", workflow_type="technical",
        process_id=99999, round_no=1,
    )
    db.add(s)
    db.commit()
    assert pl._process_section(db, s) == ""


def test_process_section_with_memory(db) -> None:
    from realmock.domains.interview.models import InterviewProcess, InterviewSession
    from realmock.domains.interview.process.process_memory import dump_memory, empty_memory

    mem = empty_memory()
    mem["rounds"] = [{"round_no": 1, "session_id": 1, "result": "passed",
                      "digest": {"summary": "good round", "topics_covered": ["Redis"]}}]
    proc = InterviewProcess(
        profile_id=1, role="Backend", level="Senior", company="bytedance",
        max_rounds=3, memory=dump_memory(mem),
    )
    db.add(proc)
    db.commit()
    db.refresh(proc)
    s = InterviewSession(
        profile_id=1, role="Backend", level="Senior", company="bytedance",
        workflow_type="technical", process_id=proc.id, round_no=2,
    )
    db.add(s)
    db.commit()
    out = pl._process_section(db, s)
    assert "round 2" in out.lower()


def test_round_pass_criteria_none_and_match() -> None:
    proc = SimpleNamespace(round_plan="{}", round_plan_status="")
    assert pl._round_pass_criteria(proc, 1) == ""
    # Ready plan with matching round_no
    from realmock.domains.interview.process.round_plan_schema import RoundPlan, PlannedRound

    plan = RoundPlan(rounds=[
        PlannedRound(round_no=1, kind="tech_1", workflow_type="technical",
                     personality="professional", interview_style="deep_dive",
                     strictness=3, focus="f", label="l", pass_criteria="Pass when solid"),
    ])
    proc2 = SimpleNamespace(
        round_plan=json.dumps(plan.to_dict()), round_plan_status="ready", id=1,
    )
    assert pl._round_pass_criteria(proc2, 1) == "Pass when solid"
    assert pl._round_pass_criteria(proc2, 2) == ""


def test_round_pass_criteria_exception(monkeypatch) -> None:
    monkeypatch.setattr(
        "realmock.domains.interview.agents.planning.planner.load_round_plan",
        lambda proc: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert pl._round_pass_criteria(object(), 1) == ""


@contextmanager
def _sessions_ctx(db_obj):
    yield db_obj


@pytest.mark.asyncio
async def test_generate_plan_session_missing(monkeypatch) -> None:
    @contextmanager
    def fake_sessions():
        class _Db:
            def get(self, *a, **k):
                return None

        yield _Db()

    monkeypatch.setattr(pl, "sessions_db_session", fake_sessions)
    await pl.generate_plan_for_session(999)  # no crash


@pytest.mark.asyncio
async def test_generate_plan_already_ready(monkeypatch) -> None:
    @contextmanager
    def fake_sessions():
        class _Db:
            def get(self, *a, **k):
                return SimpleNamespace(plan_status=pl.PLAN_STATUS_READY)

        yield _Db()

    monkeypatch.setattr(pl, "sessions_db_session", fake_sessions)
    await pl.generate_plan_for_session(1)


@pytest.mark.asyncio
async def test_generate_plan_no_api_key_marks_failed(monkeypatch) -> None:
    committed: dict = {}

    class _Db:
        def get(self, *a, **k):
            return SimpleNamespace(plan_status="", plan=None)

        def commit(self):
            committed["ok"] = True

    @contextmanager
    def fake_sessions():
        yield _Db()

    monkeypatch.setattr(pl, "sessions_db_session", fake_sessions)
    monkeypatch.setattr(pl, "session_llm", lambda db, s: SimpleNamespace(api_key=""))
    await pl.generate_plan_for_session(1)
    assert committed.get("ok") is True


@pytest.mark.asyncio
async def test_generate_plan_success(monkeypatch) -> None:
    from tests.fakes import FakeLLMClient

    row = SimpleNamespace(
        plan_status="", plan=None, profile_id=1, resume_id=None,
        role="Backend", level="Senior", company="bytedance",
        workflow_type="technical", personality="professional", strictness=3,
        interview_style="deep_dive", ui_locale="zh-CN",
    )

    class _Db:
        def get(self, *a, **k):
            return row

        def commit(self):
            row.committed = True

    @contextmanager
    def fake_sessions():
        yield _Db()

    @contextmanager
    def fake_api():
        yield object()

    monkeypatch.setattr(pl, "sessions_db_session", fake_sessions)
    monkeypatch.setattr(pl, "api_db_session", fake_api)
    monkeypatch.setattr(
        pl, "session_llm", lambda db, s: FakeLLMClient(json_payload=_valid_plan_dict(), api_key="k")
    )
    monkeypatch.setattr(pl, "get_user_profile", lambda db, pid: None)
    monkeypatch.setattr(pl, "get_resume_agent_payload", lambda db, rid: None)
    monkeypatch.setattr(pl, "get_company_context", lambda cid: "ctx")
    monkeypatch.setattr(pl, "_process_section", lambda db, s: "")
    await pl.generate_plan_for_session(42)
    assert row.plan_status == pl.PLAN_STATUS_READY
    assert json.loads(row.plan)["source"] == "agent"


@pytest.mark.asyncio
async def test_generate_plan_llm_timeout_marks_failed(monkeypatch) -> None:
    row = SimpleNamespace(plan_status="", plan=None, profile_id=1, resume_id=None,
                          role="R", level="L", company="C", workflow_type="technical",
                          personality="professional", strictness=3, interview_style="deep_dive",
                          ui_locale=None)

    class _Db:
        def get(self, *a, **k):
            return row

        def commit(self):
            pass

    @contextmanager
    def fake_sessions():
        yield _Db()

    @contextmanager
    def fake_api():
        yield object()

    class _TimeoutLLM:
        api_key = "k"

        async def chat_json(self, *a, **k):
            raise asyncio.TimeoutError()

    monkeypatch.setattr(pl, "sessions_db_session", fake_sessions)
    monkeypatch.setattr(pl, "api_db_session", fake_api)
    monkeypatch.setattr(pl, "session_llm", lambda db, s: _TimeoutLLM())
    monkeypatch.setattr(pl, "get_user_profile", lambda db, pid: None)
    monkeypatch.setattr(pl, "get_resume_agent_payload", lambda db, rid: None)
    monkeypatch.setattr(pl, "get_company_context", lambda cid: "")
    monkeypatch.setattr(pl, "_process_section", lambda db, s: "")
    await pl.generate_plan_for_session(1)
    assert row.plan_status == pl.PLAN_STATUS_FAILED


@pytest.mark.asyncio
async def test_generate_plan_generic_exception_marks_failed(monkeypatch) -> None:
    row = SimpleNamespace(plan_status="", plan=None, profile_id=1, resume_id=None,
                          role="R", level="L", company="C", workflow_type="technical",
                          personality="professional", strictness=3, interview_style="deep_dive",
                          ui_locale=None)

    class _Db:
        def get(self, *a, **k):
            return row

        def commit(self):
            pass

    @contextmanager
    def fake_sessions():
        yield _Db()

    @contextmanager
    def fake_api():
        yield object()

    class _BoomLLM:
        api_key = "k"

        async def chat_json(self, *a, **k):
            raise RuntimeError("down")

    monkeypatch.setattr(pl, "sessions_db_session", fake_sessions)
    monkeypatch.setattr(pl, "api_db_session", fake_api)
    monkeypatch.setattr(pl, "session_llm", lambda db, s: _BoomLLM())
    monkeypatch.setattr(pl, "get_user_profile", lambda db, pid: None)
    monkeypatch.setattr(pl, "get_resume_agent_payload", lambda db, rid: None)
    monkeypatch.setattr(pl, "get_company_context", lambda cid: "")
    monkeypatch.setattr(pl, "_process_section", lambda db, s: "")
    await pl.generate_plan_for_session(1)
    assert row.plan_status == pl.PLAN_STATUS_FAILED


@pytest.mark.asyncio
async def test_generate_plan_outer_crash_marks_failed(monkeypatch) -> None:
    def boom():
        raise RuntimeError("outer")

    monkeypatch.setattr(pl, "sessions_db_session", boom)

    second: dict = {}

    @contextmanager
    def fake_second():
        class _Db:
            def get(self, *a, **k):
                return SimpleNamespace(plan_status="")

            def commit(self):
                second["marked"] = True

        yield _Db()

    # First call raises; second call (failure marking) succeeds.
    calls = {"n": 0}

    def switching():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("outer")
        return fake_second()

    monkeypatch.setattr(pl, "sessions_db_session", switching)
    await pl.generate_plan_for_session(1)
    assert second.get("marked") is True


@pytest.mark.asyncio
async def test_wait_for_plan_ready_immediate() -> None:
    s = SimpleNamespace(plan_status=pl.PLAN_STATUS_READY)
    await pl.wait_for_plan_ready(SimpleNamespace(), s, timeout_seconds=0.01)


@pytest.mark.asyncio
async def test_wait_for_plan_ready_polls_then_ready(monkeypatch) -> None:
    s = SimpleNamespace(plan_status="", id=1)
    states = [pl.PLAN_STATUS_PENDING, pl.PLAN_STATUS_READY]
    idx = {"i": 0}

    class _Db:
        def expire(self, *a):
            pass

        def refresh(self, sess):
            idx["i"] += 1
            sess.plan_status = states[min(idx["i"], 1)]

    monkeypatch.setattr(pl, "_POLL_INTERVAL_SECONDS", 0.001)
    await pl.wait_for_plan_ready(_Db(), s, timeout_seconds=5)
    assert s.plan_status == pl.PLAN_STATUS_READY


@pytest.mark.asyncio
async def test_wait_for_plan_ready_timeout(monkeypatch) -> None:
    s = SimpleNamespace(plan_status="", id=2)

    class _Db:
        def expire(self, *a):
            pass

        def refresh(self, sess):
            pass

    monkeypatch.setattr(pl, "_POLL_INTERVAL_SECONDS", 0.001)
    await pl.wait_for_plan_ready(_Db(), s, timeout_seconds=0.01)
    assert s.plan_status == pl.PLAN_STATUS_PENDING


@pytest.mark.asyncio
async def test_ensure_plan_existing(monkeypatch) -> None:
    s = SimpleNamespace(plan_status=pl.PLAN_STATUS_READY, plan=json.dumps(_valid_plan_dict()))
    out = await pl.ensure_plan(SimpleNamespace(), s)
    assert out is not None
    assert len(out.steps) >= 8


@pytest.mark.asyncio
async def test_ensure_plan_fallback_persisted(monkeypatch) -> None:
    committed: dict = {}

    class _Db:
        def commit(self):
            committed["ok"] = True

        def rollback(self):
            pass

    s = SimpleNamespace(plan_status=pl.PLAN_STATUS_FAILED, plan="{}", workflow_type="technical", id=1)
    out = await pl.ensure_plan(_Db(), s)
    assert out is not None
    assert s.plan_status == pl.PLAN_STATUS_READY
    assert committed.get("ok") is True


@pytest.mark.asyncio
async def test_ensure_plan_persist_failure_returns_none() -> None:
    class _Db:
        def commit(self):
            raise RuntimeError("db down")

        def rollback(self):
            pass

    s = SimpleNamespace(plan_status=pl.PLAN_STATUS_FAILED, plan="{}", workflow_type="technical", id=1)
    assert await pl.ensure_plan(_Db(), s) is None


@pytest.mark.asyncio
async def test_ensure_plan_waits_for_pending(monkeypatch) -> None:
    async def fake_wait(db, sess, timeout_seconds=45.0):
        sess.plan_status = pl.PLAN_STATUS_FAILED

    monkeypatch.setattr(pl, "wait_for_plan_ready", fake_wait)

    class _Db:
        def commit(self):
            pass

        def rollback(self):
            pass

    s = SimpleNamespace(plan_status=pl.PLAN_STATUS_PENDING, plan="{}", workflow_type="technical", id=1)
    out = await pl.ensure_plan(_Db(), s)
    assert out is not None


# ---- startup / migrations ----















# ---- company research integration ---------------------------------------------


def _plan_row(**overrides) -> SimpleNamespace:
    row = SimpleNamespace(
        plan_status="", plan=None, profile_id=1, resume_id=None,
        role="Backend", level="Senior", company="Acme",
        workflow_type="technical", personality="professional", strictness=3,
        interview_style="deep_dive", ui_locale="zh-CN",
    )
    for k, v in overrides.items():
        setattr(row, k, v)
    return row


class _RecordingJSONLLM(FakeLLMClient):
    def __init__(self, payload):
        super().__init__(json_payload=payload, api_key="k")
        self.json_calls: list = []

    async def chat_json(self, messages, temperature=0.3):
        self.json_calls.append(messages)
        return self.json_payload


def _patch_planner_io(monkeypatch, row, llm) -> None:
    @contextmanager
    def fake_api():
        yield object()

    class _Db:
        def get(self, *a, **k):
            return row

        def commit(self):
            pass

    @contextmanager
    def fake_sessions_db():
        yield _Db()

    monkeypatch.setattr(pl, "sessions_db_session", fake_sessions_db)
    monkeypatch.setattr(pl, "api_db_session", fake_api)
    monkeypatch.setattr(pl, "session_llm", lambda db, s: llm)
    monkeypatch.setattr(pl, "get_user_profile", lambda db, pid: None)
    monkeypatch.setattr(pl, "get_resume_agent_payload", lambda db, rid: None)
    monkeypatch.setattr(pl, "_process_section", lambda db, s: "")


@pytest.mark.asyncio
async def test_generate_plan_standalone_custom_company_researches(monkeypatch) -> None:
    row = _plan_row()
    llm = _RecordingJSONLLM(_valid_plan_dict())
    _patch_planner_io(monkeypatch, row, llm)
    monkeypatch.setattr(pl, "get_company_context", lambda cid: "ctx")

    async def fake_research(llm_arg, **kwargs):
        assert kwargs["company"] == "Acme"
        return "STANDALONE-DIGEST"

    monkeypatch.setattr(pl, "research_company_context", fake_research)
    await pl.generate_plan_for_session(7)
    assert row.company_research == "STANDALONE-DIGEST"
    assert row.plan_status == pl.PLAN_STATUS_READY
    assert "STANDALONE-DIGEST" in llm.json_calls[0][1]["content"]


@pytest.mark.asyncio
async def test_generate_plan_standalone_research_failure_still_plans(monkeypatch) -> None:
    row = _plan_row()
    llm = _RecordingJSONLLM(_valid_plan_dict())
    _patch_planner_io(monkeypatch, row, llm)
    monkeypatch.setattr(pl, "get_company_context", lambda cid: "ctx")

    async def failed_research(llm_arg, **kwargs):
        return None

    monkeypatch.setattr(pl, "research_company_context", failed_research)
    await pl.generate_plan_for_session(7)
    assert row.company_research == ""
    assert row.plan_status == pl.PLAN_STATUS_READY


@pytest.mark.asyncio
async def test_generate_plan_catalog_company_skips_research(monkeypatch) -> None:
    row = _plan_row(company="bytedance")
    llm = _RecordingJSONLLM(_valid_plan_dict())
    _patch_planner_io(monkeypatch, row, llm)
    monkeypatch.setattr(pl, "get_company_context", lambda cid: "ctx")

    async def fail_research(llm_arg, **kwargs):
        raise AssertionError("catalog companies must not research inline")

    monkeypatch.setattr(pl, "research_company_context", fail_research)
    await pl.generate_plan_for_session(7)
    assert row.plan_status == pl.PLAN_STATUS_READY


@pytest.mark.asyncio
async def test_generate_plan_process_round_reuses_process_digest(monkeypatch) -> None:
    row = _plan_row(process_id=11, round_no=2)
    proc = SimpleNamespace(company_research="PROC-DIGEST")
    llm = _RecordingJSONLLM(_valid_plan_dict())

    @contextmanager
    def fake_sessions():
        yield row

    class _Query:
        def filter(self, *a, **k):
            return self

        def first(self):
            return proc

    class _Db:
        def get(self, *a, **k):
            return row

        def query(self, *a, **k):
            return _Query()

        def commit(self):
            pass

    @contextmanager
    def fake_sessions_db():
        yield _Db()

    @contextmanager
    def fake_api():
        yield object()

    monkeypatch.setattr(pl, "sessions_db_session", fake_sessions_db)
    monkeypatch.setattr(pl, "api_db_session", fake_api)
    monkeypatch.setattr(pl, "session_llm", lambda db, s: llm)
    monkeypatch.setattr(pl, "get_user_profile", lambda db, pid: None)
    monkeypatch.setattr(pl, "get_resume_agent_payload", lambda db, rid: None)
    monkeypatch.setattr(pl, "_process_section", lambda db, s: "")
    monkeypatch.setattr(pl, "get_company_context", lambda cid: "ctx")

    async def fail_research(llm_arg, **kwargs):
        raise AssertionError("process rounds must not research inline")

    monkeypatch.setattr(pl, "research_company_context", fail_research)
    await pl.generate_plan_for_session(7)
    assert row.plan_status == pl.PLAN_STATUS_READY
    assert "PROC-DIGEST" in llm.json_calls[0][1]["content"]
