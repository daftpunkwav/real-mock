"""Round-compaction tests for realmock.domains.prep.agents.round_compaction.

Covers: prefix_fingerprint fallback and compact_current_round guard/failure branches
Conventions: No real LLM; context builders faked; rate limits reset per test
"""
from __future__ import annotations
from types import SimpleNamespace
import pytest

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()

def test_prefix_fingerprint_never_raises(monkeypatch) -> None:
    import hashlib

    from realmock.domains.prep.agents.round_compaction import prefix_fingerprint

    assert prefix_fingerprint([], []) != ""
    monkeypatch.setattr(hashlib, "sha256", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("h")))
    assert prefix_fingerprint([{"role": "system", "content": "s"}], []) == ""

@pytest.mark.asyncio
async def test_compact_current_round_guards(monkeypatch) -> None:
    from realmock.domains.prep.agents.round_compaction import compact_current_round
    from realmock.domains.prep.agents.turn_state import TurnState
    from realmock.platform.capabilities.ai.agent import WorkingMemory

    mem = WorkingMemory()
    fake_llm = SimpleNamespace(context_window=8000)

    # Already used this turn.
    st = TurnState()
    st.compact_used = True
    out = await compact_current_round(
        messages=[], context_window=8000, memory=mem, llm=fake_llm,  # type: ignore[arg-type]
        reply_locale="zh-CN", turn_state=st, objective_line="", resume_id=None, args={},
    )
    assert "already ran" in out.text
    assert out.messages is None

    # Below usage floor refuses without an LLM call.
    st2 = TurnState()
    out2 = await compact_current_round(
        messages=[{"role": "user", "content": "hi"}], context_window=8000,
        memory=mem, llm=fake_llm,  # type: ignore[arg-type]
        reply_locale="zh-CN", turn_state=st2, objective_line="", resume_id=None, args={},
    )
    assert "not needed yet" in out2.text

    # No user turn to protect.
    st3 = TurnState()
    big = [{"role": "assistant", "content": "x" * 5000}]
    out3 = await compact_current_round(
        messages=big, context_window=100, memory=mem, llm=fake_llm,  # type: ignore[arg-type]
        reply_locale="zh-CN", turn_state=st3, objective_line="", resume_id=None, args={},
    )
    assert "No user turn" in out3.text

@pytest.mark.asyncio
async def test_compact_current_round_failure_branch(monkeypatch) -> None:
    import realmock.domains.prep.agents.round_compaction as rc_mod
    from realmock.domains.prep.agents.turn_state import TurnState
    from realmock.platform.capabilities.ai.agent import WorkingMemory

    async def _boom(*args, **kwargs):
        raise RuntimeError("sk-secret-summarizer-down")

    monkeypatch.setattr(rc_mod, "build_turn_context", _boom)
    mem = WorkingMemory()
    fake_llm = SimpleNamespace(context_window=8000)
    st = TurnState()
    messages = [
        {"role": "user", "content": "first " + "x" * 2000},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "second question here"},
    ]
    out = await rc_mod.compact_current_round(
        messages=messages, context_window=500, memory=mem, llm=fake_llm,  # type: ignore[arg-type]
        reply_locale="zh-CN", turn_state=st, objective_line="obj", resume_id=None, args={},
    )
    assert "Compaction failed" in out.text
    assert "continuing with full history" in out.text
    assert out.messages is None
