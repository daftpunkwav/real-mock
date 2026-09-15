"""Session prompt final gaps tests for src/realmock/domains/interview/agents/session_prompt.py.

Covers: empty-render identity, opening estimate failure, refresh-head profile compact
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


# ---- prompt_assembler (57, 81-82, 109-110, 117, 133, 144) ----










# ---- history_compaction (118-119, 138-139, 152-153) ----


def _fold_agent(n=12):
    messages: list[dict[str, Any]] = [{"role": "system", "content": "rules"}]
    for i in range(n):
        messages.append({"role": "assistant", "content": f"Q{i} " + "x" * 200})
        messages.append({"role": "user", "content": f"A{i} " + "y" * 200})
    return SimpleNamespace(messages=messages, agent_state={})








# ---- past_records (29-31, 68-69) ----




# ---- session_prompt (237, 315-316, 397-398) ----


def _sp_mixin(**overrides):
    from realmock.domains.interview.agents.session_prompt import SessionPromptMixin

    m = SessionPromptMixin()
    m.session = SimpleNamespace(
        role="Backend",
        level="Senior",
        company="bytedance",
        workflow_type="technical",
        personality="professional",
        strictness=3,
        interview_style="deep_dive",
        resume_id=1,
        profile_id=1,
        round_no=1,
        process_id=None,
    )
    m.agent_state = {}
    m.messages = [{"role": "system", "content": "base"}]
    m.workflow = SimpleNamespace(id="technical", name="Technical", phases=[])
    m.plan = None
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


def test_session_prompt_empty_render_returns_identity(monkeypatch) -> None:
    m = _sp_mixin()
    m.session.process_id = 9
    m.session.round_no = 2
    proc = SimpleNamespace(id=9, max_rounds=3, workflow_type="technical", memory="{}")

    @contextmanager
    def _fake_sess():
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
        "realmock.domains.interview.agents.session_prompt.sessions_db_session", _fake_sess
    )
    monkeypatch.setattr(
        "realmock.domains.interview.agents.session_prompt.load_memory", lambda raw: {}
    )
    monkeypatch.setattr(
        "realmock.domains.interview.agents.session_prompt.render_for_prompt", lambda mem: ""
    )
    out = m._process_round_section()
    assert "round" in out.lower() or out != ""


def test_session_prompt_opening_estimate_failure(monkeypatch) -> None:
    m = _sp_mixin()
    monkeypatch.setattr(m, "get_candidate", lambda db: None)
    monkeypatch.setattr(m, "get_user_profile", lambda db: None)
    monkeypatch.setattr(
        "realmock.domains.interview.agents.session_prompt.get_company_context",
        lambda cid: "ctx",
    )
    monkeypatch.setattr(
        "realmock.domains.interview.agents.session_prompt.build_system_prompt",
        lambda *a, **k: "SYSTEM ",
    )
    m.current_phase = lambda: SimpleNamespace(id="identity_check")  # type: ignore[method-assign]

    def _boom(messages):
        raise RuntimeError("tok down")

    monkeypatch.setattr(
        "realmock.platform.capabilities.ai.context.estimation.estimate_messages_tokens",
        _boom,
    )
    out = m.build_opening_prompt(db=None)  # type: ignore[arg-type]
    assert out.startswith("SYSTEM ")


def test_session_prompt_refresh_head_loads_profile(monkeypatch) -> None:
    from realmock.domains.interview.agents import session_prompt as mod

    m = _sp_mixin()
    m.messages = [
        {
            "role": "system",
            "content": "head ## Candidate profile FULL\nbody\n## Current phase\nold\n## Full flow\nflow",
        }
    ]
    phase = SimpleNamespace(id="p1", name="Coding", description="code", min_questions=1, max_questions=3)
    monkeypatch.setattr(mod, "needs_compact_candidate", lambda phase: True)
    monkeypatch.setattr(mod, "compact_candidate_block", lambda prof, cand: "COMPACT")

    @contextmanager
    def _fake_api():
        yield SimpleNamespace()

    monkeypatch.setattr(mod, "api_db_session", _fake_api)
    monkeypatch.setattr(
        mod, "get_user_profile", lambda db, pid: SimpleNamespace(name="Ada")
    )
    m.refresh_system_head(phase, profile=None, candidate={"x": 1})
    assert "COMPACT" in m.messages[0]["content"]


# ---- tool_guard (74, 109-110, 116, 127) ----




