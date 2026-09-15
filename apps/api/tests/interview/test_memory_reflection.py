"""Memory reflection tests for src/realmock/domains/interview/agents/memory/reflection.py.

Covers: reflect_on_dialogue skip/call/parse/cap/swallow branches
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import pytest

from realmock.domains.interview.agents.memory.cognitive_graph import (
    CognitiveMemoryGraph,
)
from realmock.domains.interview.agents.memory.reflection import reflect_on_dialogue
from realmock.platform.capabilities.ai.llm.client import LLMClient


def _fallback_llm() -> LLMClient:
    return LLMClient(api_base="https://api.example.com", api_key="", model="gpt-4")






























# ---- reflection ----

@pytest.mark.asyncio
async def test_reflect_empty_turns_no_call() -> None:
    from tests.fakes import FakeLLMClient

    class _Counting(FakeLLMClient):
        def __init__(self) -> None:
            super().__init__(api_key="k")
            self.calls = 0

        async def chat_json(self, messages, temperature=0.2):  # type: ignore[override]
            self.calls += 1
            return {}

    llm = _Counting()
    graph = CognitiveMemoryGraph()
    await reflect_on_dialogue(llm, graph, [], 1)  # type: ignore[arg-type]
    assert llm.calls == 0
    assert graph.nodes == {}


@pytest.mark.asyncio
async def test_reflect_no_api_key_no_call() -> None:
    llm = _fallback_llm()
    graph = CognitiveMemoryGraph()
    await reflect_on_dialogue(llm, graph, [{"assistant": "q", "user": "a"}], 1)
    assert graph.nodes == {}


@pytest.mark.asyncio
async def test_reflect_invalid_raw_no_crash() -> None:
    from tests.fakes import FakeLLMClient

    class _Shim(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.2):  # type: ignore[override]
            return None  # type: ignore[return-value]

    graph = CognitiveMemoryGraph()
    await reflect_on_dialogue(_Shim(api_key="k"), graph, [{"assistant": "q", "user": "a"}], 1)  # type: ignore[arg-type]
    assert graph.nodes == {}


@pytest.mark.asyncio
async def test_reflect_records_valid_and_skips_bad() -> None:
    from tests.fakes import FakeLLMClient

    payload = {
        "reflections": [
            {"topic": "MySQL Index", "category": "database", "status": "verified",
             "claim": "knows B+ tree", "finding": "solid", "confidence": 0.9},
            {"topic": "", "status": "verified"},  # skipped: empty topic
            {"topic": "Redis", "status": "bogus"},  # skipped: bad status
            "not-a-dict",  # skipped
            {"topic": "Cache", "category": "database", "status": "suspicious",
             "claim": "vague", "finding": "buzzwords", "confidence": "not-a-float"},
        ],
        "suggested_next_probe": "  probe cache penetration deeper  ",
    }

    class _Shim(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.2):  # type: ignore[override]
            return dict(payload)

    graph = CognitiveMemoryGraph()
    await reflect_on_dialogue(
        _Shim(api_key="k"), graph,  # type: ignore[arg-type]
        [{"turn": 1, "assistant": "Explain index", "user": "B+ tree..."}], 2,
    )
    assert "mysql index" in graph.nodes
    assert "cache" in graph.nodes
    assert graph.nodes["cache"].confidence == 0.8
    assert graph.working_memory.pending_probes == ["probe cache penetration deeper"]


@pytest.mark.asyncio
async def test_reflect_caps_pending_probes_at_four() -> None:
    from tests.fakes import FakeLLMClient

    class _Shim(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.2):  # type: ignore[override]
            return {"reflections": [], "suggested_next_probe": "new probe"}

    graph = CognitiveMemoryGraph()
    graph.working_memory.pending_probes = ["p1", "p2", "p3", "p4"]
    await reflect_on_dialogue(
        _Shim(api_key="k"), graph, [{"assistant": "q", "user": "a"}], 1  # type: ignore[arg-type]
    )
    assert len(graph.working_memory.pending_probes) == 4
    assert graph.working_memory.pending_probes[-1] == "new probe"


@pytest.mark.asyncio
async def test_reflect_blank_probe_not_appended() -> None:
    from tests.fakes import FakeLLMClient

    class _Shim(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.2):  # type: ignore[override]
            return {"reflections": [], "suggested_next_probe": "   "}

    graph = CognitiveMemoryGraph()
    await reflect_on_dialogue(
        _Shim(api_key="k"), graph, [{"assistant": "q", "user": "a"}], 1  # type: ignore[arg-type]
    )
    assert graph.working_memory.pending_probes == []


@pytest.mark.asyncio
async def test_reflect_llm_raises_is_swallowed() -> None:
    from tests.fakes import FakeLLMClient

    class _Boom(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.2):  # type: ignore[override]
            raise RuntimeError("down")

    graph = CognitiveMemoryGraph()
    await reflect_on_dialogue(
        _Boom(api_key="k"), graph, [{"assistant": "q", "user": "a"}], 1  # type: ignore[arg-type]
    )
    assert graph.nodes == {}
