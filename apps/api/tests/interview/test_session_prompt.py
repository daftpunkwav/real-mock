"""Session prompt tests for src/realmock/domains/interview/agents/session_prompt.py.

Covers: config, learning, memory, scores, flow, process rounds, opening, refresh head
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from realmock.domains.interview.agents.session_prompt import (
    _MEMORY_SECTION_MARKER,
    SessionPromptMixin,
)


def _mixin(**overrides):
    m = SessionPromptMixin()
    m.session = SimpleNamespace(
        role="Backend", level="Senior", company="bytedance",
        workflow_type="technical", personality="professional", strictness=3,
        interview_style="deep_dive", resume_id=1, profile_id=1,
        round_no=1, process_id=None,
    )
    m.agent_state = {}
    m.messages = [{"role": "system", "content": "base"}]
    m.workflow = SimpleNamespace(id="technical", name="Technical", phases=[])
    m.plan = None
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


def test_get_config_validates_literals() -> None:
    m = _mixin()
    cfg = m.get_config()
    assert cfg.role == "Backend"
    assert cfg.workflow_type == "technical"
    assert cfg.personality == "professional"


def test_get_config_legacy_workflow_falls_back() -> None:
    m = _mixin()
    m.session.workflow_type = None
    m.session.personality = None
    m.session.interview_style = None
    cfg = m.get_config()
    assert cfg.workflow_type == "technical"


def test_system_learning_no_provider() -> None:
    m = _mixin()
    m.system_insights_provider = None
    assert m._system_learning_section() == ""


def test_system_learning_provider_raises() -> None:
    m = _mixin()
    m.system_insights_provider = lambda **kw: (_ for _ in ()).throw(RuntimeError("boom"))
    assert m._system_learning_section() == ""


def test_system_learning_low_avg_and_probes() -> None:
    m = _mixin()
    m.system_insights_provider = lambda **kw: {
        "avg_scores_by_company": {"bytedance": 65},
        "recent_probes": [
            {"company": "bytedance", "role": "Backend", "point": "cache consistency weak"},
            {"company": "other", "role": "other", "point": "generic probe"},
        ],
    }
    out = m._system_learning_section()
    assert "65" in out
    assert "cache consistency" in out
    assert "System learning summary" in out


def test_system_learning_high_avg_no_section() -> None:
    m = _mixin()
    m.system_insights_provider = lambda **kw: {
        "avg_scores_by_company": {"bytedance": 95}, "recent_probes": [],
    }
    assert m._system_learning_section() == ""


def test_system_learning_skips_non_dict_probes() -> None:
    m = _mixin()
    m.system_insights_provider = lambda **kw: {
        "avg_scores_by_company": {}, "recent_probes": ["bad", 42],
    }
    assert m._system_learning_section() == ""


def test_memory_section_empty() -> None:
    m = _mixin()
    m.agent_state = {}
    m.cognitive_memory = None  # type: ignore[attr-defined]
    # WorkingMemory.from_state({}) renders empty -> ""
    assert m._memory_section() == ""


def test_memory_section_with_asked_questions() -> None:
    m = _mixin()
    m.agent_state = {"asked_questions": ["What is Redis?"]}
    m.cognitive_memory = None  # type: ignore[attr-defined]
    out = m._memory_section()
    assert _MEMORY_SECTION_MARKER in out
    assert "Redis" in out


def test_memory_section_with_cognitive_graph() -> None:
    from realmock.domains.interview.agents.memory.cognitive_graph import (
        CognitiveMemoryGraph,
        CompetencyStatus,
    )

    m = _mixin()
    m.agent_state = {}
    g = CognitiveMemoryGraph()
    g.record_finding(
        topic="Redis", category="database", status=CompetencyStatus.VERIFIED,
        claim="knows", finding="solid", turn_index=1, confidence=0.9,
    )
    m.cognitive_memory = g  # type: ignore[attr-defined]
    out = m._memory_section()
    assert "Redis" in out


def test_score_section_empty() -> None:
    m = _mixin()
    assert m._score_section() == ""


def test_score_section_renders_trajectory() -> None:
    m = _mixin()
    m.agent_state = {
        "turn_scores": [
            {"rating": 4, "brief": "good depth", "weak_points": ["cache", "mq"]},
            "not-a-dict",
            {"rating": 0, "brief": "", "weak_points": []},
        ]
    }
    out = m._score_section()
    assert "4/5" in out
    assert "good depth" in out
    assert "cache" in out


def test_flow_view_static_and_planned() -> None:
    m = _mixin()
    assert m._flow_view() is m.workflow
    plan = SimpleNamespace(round_note="Round 1", steps=[1, 2], source="agent")
    m.plan = plan
    view = m._flow_view()
    assert view.id == "planned"
    assert "Round 1" in view.name


def test_plan_is_agent_authored() -> None:
    m = _mixin()
    assert m._plan_is_agent_authored() is False
    m.plan = SimpleNamespace(source="fallback")
    assert m._plan_is_agent_authored() is False
    m.plan = SimpleNamespace(source="agent")
    assert m._plan_is_agent_authored() is True


def test_round_identity_none() -> None:
    m = _mixin()
    assert m._round_identity_section(None) == ""


def test_round_identity_renders() -> None:
    m = _mixin()
    step = SimpleNamespace(
        label="Tech 1", round_no=1, personality="professional",
        interview_style="deep_dive", strictness=3, focus="projects",
    )
    out = m._round_identity_section(step)
    assert "Tech 1" in out
    assert "projects" in out


def test_process_round_no_process() -> None:
    m = _mixin()
    assert m._process_round_section() == ""


def test_process_round_process_missing(monkeypatch) -> None:
    from contextlib import contextmanager

    m = _mixin()
    m.session.process_id = 999

    @contextmanager
    def fake_sessions():
        class _Db:
            def query(self, *a, **k):
                class _Q:
                    def filter(self, *a, **k):
                        return self

                    def first(self):
                        return None

                return _Q()

        yield _Db()

    monkeypatch.setattr(
        "realmock.domains.interview.agents.session_prompt.sessions_db_session", fake_sessions
    )
    assert m._process_round_section() == ""


def test_process_round_exception_returns_empty(monkeypatch) -> None:
    m = _mixin()
    m.session.process_id = 1

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(
        "realmock.domains.interview.agents.session_prompt.sessions_db_session", boom
    )
    assert m._process_round_section() == ""


def test_process_round_with_memory_and_identity(monkeypatch) -> None:
    from contextlib import contextmanager

    from realmock.domains.interview.protocols import process_memory as pm

    m = _mixin()
    m.session.process_id = 5
    m.session.round_no = 2
    proc = SimpleNamespace(id=5, max_rounds=3, workflow_type="technical", memory=pm.dump_memory({
        "schema": pm.MEMORY_SCHEMA, "rounds": [
            {"round_no": 1, "session_id": 1, "result": "passed",
             "digest": {"summary": "good", "topics_covered": ["Redis"]}},
        ], "final": None,
    }))

    @contextmanager
    def fake_sessions():
        class _Db:
            def query(self, *a, **k):
                class _Q:
                    def filter(self, *a, **k):
                        return self

                    def first(self):
                        return proc

                return _Q()

        yield _Db()

    monkeypatch.setattr(
        "realmock.domains.interview.agents.session_prompt.sessions_db_session", fake_sessions
    )
    out = m._process_round_section()
    assert "Prior rounds memory" in out
    assert "Redis" in out


def test_flow_language_defaults_and_agent() -> None:
    m = _mixin()
    assert m._flow_language() == "zh"
    m.plan = SimpleNamespace(source="fallback", language="en")
    assert m._flow_language() == "zh"
    m.plan = SimpleNamespace(source="agent", language="en")
    assert m._flow_language() == "en"


def test_opening_section_styles() -> None:
    m = _mixin()
    m.plan = None
    assert "identity_confirm" in m._opening_section()
    m.plan = SimpleNamespace(opening=SimpleNamespace(style="resume_ack", note="Ada + Redis"))
    out = m._opening_section()
    assert "resume_ack" in out and "Ada" in out
    m.plan = SimpleNamespace(opening=SimpleNamespace(style="casual_warmup", note=""))
    assert "casual_warmup" in m._opening_section()


def test_build_opening_prompt_assembles(monkeypatch) -> None:
    m = _mixin()
    monkeypatch.setattr(m, "get_candidate", lambda db: None)
    monkeypatch.setattr(m, "get_user_profile", lambda db: None)
    monkeypatch.setattr(
        "realmock.domains.interview.agents.session_prompt.get_company_context", lambda cid: "ctx"
    )
    monkeypatch.setattr(
        "realmock.domains.interview.agents.session_prompt.build_system_prompt",
        lambda *a, **k: "SYSTEM ",
    )
    m.current_phase = lambda: SimpleNamespace(id="identity_check")  # type: ignore[method-assign]
    out = m.build_opening_prompt(db=None)  # type: ignore[arg-type]
    assert out.startswith("SYSTEM ")
    assert "Opening style" in out


def test_strip_memory_section() -> None:
    content = "head\n\n## Session structured memory (do not repeat asked questions)\nmem"
    assert _mixin()._strip_memory_section(content) == "head"
    legacy = "head\n\n## Conversation structured memory (do not repeat questions that have been asked)\nmem"
    assert _mixin()._strip_memory_section(legacy) == "head"
    assert _mixin()._strip_memory_section("plain  ") == "plain"


def test_refresh_system_memory_no_messages() -> None:
    m = _mixin()
    m.messages = []
    m.refresh_system_memory()  # no crash
    assert m.messages == []


def test_refresh_system_memory_non_system_head() -> None:
    m = _mixin()
    m.messages = [{"role": "user", "content": "hi"}]
    m.refresh_system_memory()
    assert m.messages[0]["content"] == "hi"


def test_refresh_system_memory_non_str_content() -> None:
    m = _mixin()
    m.messages = [{"role": "system", "content": {"bad": 1}}]  # type: ignore[dict-item]
    m.refresh_system_memory()
    assert m.messages[0]["content"] == {"bad": 1}


def test_refresh_system_memory_replaces_memory() -> None:
    m = _mixin()
    m.agent_state = {"asked_questions": ["new Q"]}
    m.cognitive_memory = None  # type: ignore[attr-defined]
    m.messages = [{"role": "system", "content": "base\n\n" + _MEMORY_SECTION_MARKER + "\nold"}]
    m.refresh_system_memory()
    assert "new Q" in m.messages[0]["content"]
    assert "old" not in m.messages[0]["content"]


def test_refresh_system_head_guards() -> None:
    m = _mixin()
    m.messages = []
    m.refresh_system_head(SimpleNamespace(id="x"))  # no crash
    m.messages = [{"role": "user", "content": "hi"}]
    m.refresh_system_head(SimpleNamespace(id="x"))
    m.messages = [{"role": "system", "content": 123}]  # type: ignore[dict-item]
    m.refresh_system_head(SimpleNamespace(id="x"))
    m.messages = [{"role": "system", "content": "no phase marker here"}]
    m.refresh_system_head(SimpleNamespace(id="x"))
    assert m.messages[0]["content"] == "no phase marker here"


@pytest.mark.asyncio
async def test_get_user_profile_and_candidate_use_api_db(monkeypatch) -> None:
    from contextlib import contextmanager

    m = _mixin()

    @contextmanager
    def fake_api():
        yield "API-DB"

    seen: dict = {}
    monkeypatch.setattr(
        "realmock.domains.interview.agents.session_prompt.api_db_session", fake_api
    )
    monkeypatch.setattr(
        "realmock.domains.interview.agents.session_prompt.get_user_profile",
        lambda db, pid: seen.update({"u": (db, pid)}) or "PROFILE",
    )
    monkeypatch.setattr(
        "realmock.domains.interview.agents.session_prompt.get_candidate_profile",
        lambda db, rid: seen.update({"c": (db, rid)}) or "CAND",
    )
    assert m.get_user_profile(None) == "PROFILE"  # type: ignore[arg-type]
    assert m.get_candidate(None) == "CAND"  # type: ignore[arg-type]
    assert seen["u"] == ("API-DB", 1)


def test_build_opening_prompt_blends_research_digest(monkeypatch) -> None:
    import realmock.domains.interview.agents.session_prompt as sp

    m = _mixin()
    monkeypatch.setattr(m, "get_candidate", lambda db: None)
    monkeypatch.setattr(m, "get_user_profile", lambda db: None)
    monkeypatch.setattr(sp, "get_company_context", lambda cid: "CATALOG")
    monkeypatch.setattr(sp, "load_session_company_research", lambda db, s: "DIGEST")

    captured: dict = {}

    def fake_build(*args, **kwargs):
        captured["ctx"] = args[2]
        return "SYSTEM "

    monkeypatch.setattr(sp, "build_system_prompt", fake_build)
    m.current_phase = lambda: SimpleNamespace(id="identity_check")  # type: ignore[method-assign]
    out = m.build_opening_prompt(db=None)  # type: ignore[arg-type]
    assert out.startswith("SYSTEM ")
    assert captured["ctx"] == "DIGEST"


def test_build_opening_prompt_keeps_catalog_without_digest(monkeypatch) -> None:
    import realmock.domains.interview.agents.session_prompt as sp

    m = _mixin()
    monkeypatch.setattr(m, "get_candidate", lambda db: None)
    monkeypatch.setattr(m, "get_user_profile", lambda db: None)
    monkeypatch.setattr(sp, "get_company_context", lambda cid: "CATALOG")

    captured: dict = {}

    def fake_build(*args, **kwargs):
        captured["ctx"] = args[2]
        return "SYSTEM "

    monkeypatch.setattr(sp, "build_system_prompt", fake_build)
    m.current_phase = lambda: SimpleNamespace(id="identity_check")  # type: ignore[method-assign]
    out = m.build_opening_prompt(db=None)  # type: ignore[arg-type]
    assert out.startswith("SYSTEM ")
    assert captured["ctx"] == "CATALOG"
