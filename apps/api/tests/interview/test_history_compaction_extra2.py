"""History compaction fold tests for src/realmock/domains/interview/agents/history_compaction.py.

Covers: fold before/after token failures, audit-log failure still adopts
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

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


@pytest.mark.asyncio
async def test_fold_before_tokens_failure(monkeypatch) -> None:
    from realmock.domains.interview.agents import history_compaction as mod

    agent = _fold_agent()
    calls = {"n": 0}

    def _est(messages):
        calls["n"] += 1
        if calls["n"] == 1:
            return 5000
        if calls["n"] == 2:
            raise RuntimeError("tok boom")
        return 10

    async def _compact(messages, window, **k):
        return messages[-4:]

    monkeypatch.setattr(mod, "estimate_messages_tokens", _est)
    monkeypatch.setattr(mod, "compact_with_summary", _compact)
    assert await mod.maybe_fold_history(agent, llm=None, context_window=2000) is True


@pytest.mark.asyncio
async def test_fold_after_tokens_failure(monkeypatch) -> None:
    from realmock.domains.interview.agents import history_compaction as mod

    agent = _fold_agent()
    calls = {"n": 0}

    def _est(messages):
        calls["n"] += 1
        if calls["n"] <= 2:
            return 5000
        raise RuntimeError("after boom")

    async def _compact(messages, window, **k):
        return messages[-4:]

    monkeypatch.setattr(mod, "estimate_messages_tokens", _est)
    monkeypatch.setattr(mod, "compact_with_summary", _compact)
    assert await mod.maybe_fold_history(agent, llm=None, context_window=2000) is True


@pytest.mark.asyncio
async def test_fold_audit_log_failure_still_adopts(monkeypatch) -> None:
    from realmock.domains.interview.agents import history_compaction as mod

    class _BadDict(dict):
        def update(self, *a, **k):
            raise RuntimeError("update down")

    agent = _fold_agent()
    agent.agent_state = _BadDict()

    async def _compact(messages, window, **k):
        return messages[-4:]

    monkeypatch.setattr(mod, "estimate_messages_tokens", lambda m: 5000)
    monkeypatch.setattr(mod, "compact_with_summary", _compact)
    # First call: budget check also uses estimate (5000 > 800) so proceeds.
    assert await mod.maybe_fold_history(agent, llm=None, context_window=2000) is True


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








# ---- tool_guard (74, 109-110, 116, 127) ----




