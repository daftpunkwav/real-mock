"""End-of-turn memory precipitation (memory_precipitate.py).

Contract:
- A short final answer never triggers the curation call;
- A negative or empty verdict writes nothing;
- A positive verdict writes exactly one memory through ``run_memory_write``
  with clamped fields and the turn-scoped idempotency key;
- Any failure is swallowed — precipitation must never break the turn.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import realmock.domains.prep.agents.memory_precipitate as mp_mod
from realmock.domains.prep.agents.memory_precipitate import precipitate_turn_memory


class _FakeLLM:
    def __init__(self, verdict: dict | None = None, error: Exception | None = None) -> None:
        self.verdict = verdict
        self.error = error
        self.calls: list[list[dict]] = []

    async def chat_json(self, messages, **kwargs):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return self.verdict


def _agent(llm: _FakeLLM) -> SimpleNamespace:
    return SimpleNamespace(llm=llm, memory=SimpleNamespace(), last_turn_id="turn-abc")


@pytest.fixture()
def _stub_env(monkeypatch: pytest.MonkeyPatch):
    """Patch out the DB memory index and the real memory-write path."""
    monkeypatch.setattr(mp_mod, "list_memories", lambda db, limit=10: [])
    writes: list[dict] = []

    async def fake_write(args, memory):
        writes.append(args)
        return "stored", []

    monkeypatch.setattr(mp_mod, "run_memory_write", fake_write)
    return writes


async def test_short_final_skips_curation(_stub_env) -> None:
    llm = _FakeLLM(verdict={"save": True, "summary": "s"})
    await precipitate_turn_memory(_agent(llm), "hi", "too short")
    assert llm.calls == []
    assert _stub_env == []


async def test_negative_verdict_writes_nothing(_stub_env) -> None:
    llm = _FakeLLM(verdict={"save": False})
    await precipitate_turn_memory(_agent(llm), "q", "a" * 100)
    assert len(llm.calls) == 1
    assert _stub_env == []


async def test_positive_verdict_writes_one_clamped_memory(_stub_env) -> None:
    verdict = {
        "save": True,
        "summary": "S" * 300,
        "user_input": "U" * 600,
        "agent_output": "A" * 600,
        "tags": [1, "ok", None, "x"],
        "origin": "agent_note",
    }
    llm = _FakeLLM(verdict=verdict)
    await precipitate_turn_memory(_agent(llm), "user text", "a" * 100)

    assert len(_stub_env) == 1
    args = _stub_env[0]
    assert args["summary"] == "S" * 200
    assert args["user_input"] == "U" * 500
    assert args["agent_output"] == "A" * 500
    # Non-string/int tags are dropped; the rest are stringified and clipped.
    assert args["tags"] == ["1", "ok", "x"]
    assert args["origin"] == "agent_note"
    assert args["idempotency_key"] == "precipitate:turn-abc"


async def test_positive_verdict_without_summary_writes_nothing(_stub_env) -> None:
    llm = _FakeLLM(verdict={"save": True, "summary": "   "})
    await precipitate_turn_memory(_agent(llm), "q", "a" * 100)
    assert _stub_env == []


async def test_llm_failure_is_swallowed(_stub_env) -> None:
    llm = _FakeLLM(error=RuntimeError("provider down"))
    # Must not raise: the user already has their answer.
    await precipitate_turn_memory(_agent(llm), "q", "a" * 100)
    assert _stub_env == []


