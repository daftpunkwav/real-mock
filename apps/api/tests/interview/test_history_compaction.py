"""Persistent interview-history folding (agents.history_compaction).

Covers: no-op on unlimited window / tiny history, fold adoption with an
LLM summary, rule-based fallback on LLM failure (never raises), and the
anti-churn cooldown (no refold without fresh turns).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from realmock.domains.interview.agents.history_compaction import maybe_fold_history


class _SummarizerLLM:
    def __init__(self, reply: str = "", error: Exception | None = None):
        self.reply = reply
        self.error = error
        self.chat_calls: list[list[dict]] = []

    async def chat(self, messages, temperature=0.7, **kwargs):
        del temperature, kwargs
        self.chat_calls.append(messages)
        if self.error is not None:
            raise self.error
        return self.reply


def _agent(turns: int = 12) -> SimpleNamespace:
    messages: list[dict] = [{"role": "system", "content": "Interview rules"}]
    for i in range(turns):
        messages.append({"role": "assistant", "content": f"Question{i}: " + "please explain" * 40})
        messages.append({"role": "user", "content": f"Answer{i}: " + "my experience shows" * 40})
    return SimpleNamespace(messages=messages, agent_state={})


@pytest.mark.asyncio
async def test_fold_noop_on_unlimited_window() -> None:
    llm = _SummarizerLLM(reply="Notes")
    agent = _agent()
    before = list(agent.messages)
    assert await maybe_fold_history(agent, llm=llm, context_window=0) is False
    assert await maybe_fold_history(agent, llm=llm, context_window=None) is False
    assert agent.messages == before
    assert llm.chat_calls == []


@pytest.mark.asyncio
async def test_fold_noop_below_budget() -> None:
    llm = _SummarizerLLM(reply="Notes")
    agent = _agent(turns=1)
    before = list(agent.messages)
    assert await maybe_fold_history(agent, llm=llm, context_window=100000) is False
    assert agent.messages == before
    assert llm.chat_calls == []


@pytest.mark.asyncio
async def test_fold_adopts_llm_minutes() -> None:
    llm = _SummarizerLLM(reply="Candidate answered Q0-Q9 on Python; weak on concurrency.")
    agent = _agent()
    before = len(agent.messages)
    assert await maybe_fold_history(agent, llm=llm, context_window=2000, keep_recent=4) is True
    assert len(agent.messages) < before
    assert llm.chat_calls, "over-budget history must trigger the summarizer"
    summaries = [
        m for m in agent.messages
        if m["role"] == "system" and str(m.get("content", "")).startswith("[Conversation Minutes]")
    ]
    assert len(summaries) == 1
    assert "concurrency" in summaries[0]["content"]
    # Recent tail stays verbatim; oldest turns are gone.
    assert not any(
        m["role"] == "assistant" and str(m.get("content", "")).startswith("Question0")
        for m in agent.messages
    )
    assert any(
        m["role"] == "assistant" and str(m.get("content", "")).startswith("Question11")
        for m in agent.messages
    )
    # Audit log is bounded and records the delta.
    log = agent.agent_state.get("compactions", [])
    assert len(log) == 1
    assert log[0]["before_msgs"] == before
    assert log[0]["after_msgs"] == len(agent.messages)


@pytest.mark.asyncio
async def test_fold_falls_back_to_digest_on_llm_failure() -> None:
    llm = _SummarizerLLM(error=RuntimeError("llm down"))
    agent = _agent()
    before = len(agent.messages)
    assert await maybe_fold_history(agent, llm=llm, context_window=2000, keep_recent=4) is True
    assert len(agent.messages) < before
    assert any(
        m["role"] == "system" and str(m.get("content", "")).startswith("[Context compression]")
        for m in agent.messages
    ), "LLM failure must degrade to a rule-based digest, never raise"


@pytest.mark.asyncio
async def test_fold_cooldown_without_fresh_turns() -> None:
    llm = _SummarizerLLM(reply="Minutes v1")
    agent = _agent()
    assert await maybe_fold_history(agent, llm=llm, context_window=2000, keep_recent=4) is True
    calls_after_first = len(llm.chat_calls)
    assert calls_after_first >= 1
    # Immediately refolding the just-folded history must be a no-op.
    assert await maybe_fold_history(agent, llm=llm, context_window=2000, keep_recent=4) is False
    assert len(llm.chat_calls) == calls_after_first
