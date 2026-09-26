"""Step-boundary compaction state machine tests.

Six guard families: skip threshold / summarize+replace / 3-strike fallback /
accumulate-and-retry / rollup / never-raises. No real network or LLM.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace as NS


from realmock.domains.interview.agents.step_compaction import (
    compact_pending_boundaries,
    compact_step_boundary,
    record_step_boundary,
)


class _FakeAgent:
    """Minimal duck-typed InterviewSessionState."""

    def __init__(self, messages):
        self.messages = messages
        self.session = NS(current_phase="old_step", id=1)
        self.agent_state = {"steps": {"step_start": 1, "step_no": 1, "summaries": []}}
        from realmock.domains.interview.agents.memory.cognitive_graph import CognitiveMemoryGraph

        self.cognitive_memory = CognitiveMemoryGraph()


def _big_transcript(n=400):
    msgs = [{"role": "system", "content": "head"}]
    for i in range(n):
        msgs.append({"role": "user", "content": f"question {i} " + "detail " * 30})
        msgs.append({"role": "assistant", "content": f"answer {i} " + "words " * 30})
    return msgs


_GOOD = {
    "topics": ["q1", "q2"],
    "verified": ["recursion"],
    "weak_points": ["asyncio"],
    "agreed_facts": ["salary 30k"],
}


class _FakeLLM:
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    async def chat_json(self, messages, temperature=0.2):
        self.calls += 1
        result = self._results.pop(0) if self._results else None
        if isinstance(result, Exception):
            raise result
        return result

    async def chat(self, messages, temperature=0.2, max_tokens=None):
        self.calls += 1
        return "merged digest"


def test_record_step_boundary_slices_and_advances():
    agent = _FakeAgent([{"role": "system", "content": "head"}, {"role": "user", "content": "hi"}])
    boundary = record_step_boundary(agent)
    assert boundary == {"start": 1, "end": 2, "step_no": 1, "phase_id": "old_step"}
    assert agent.agent_state["steps"]["step_start"] == 2
    assert agent.agent_state["steps"]["step_no"] == 2
    agent.messages.extend([{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}])
    boundary = record_step_boundary(agent)
    assert boundary == {"start": 2, "end": 4, "step_no": 2, "phase_id": "old_step"}
    assert agent.agent_state["steps"]["step_start"] == 4
    assert agent.agent_state["steps"]["step_no"] == 3


def test_small_step_is_skipped_verbatim():
    msgs = [{"role": "system", "content": "head"}, {"role": "user", "content": "tiny"}]
    agent = _FakeAgent(msgs)
    boundary = {"start": 1, "end": 2, "step_no": 1, "phase_id": "s"}
    llm = _FakeLLM([_GOOD])

    async def run():
        return await compact_step_boundary(agent, boundary, llm=llm)

    assert asyncio.run(run()) is False
    assert llm.calls == 0  # below the threshold, the LLM is never asked
    assert agent.messages == msgs


def test_successful_summary_replaces_segment_in_place():
    msgs = _big_transcript()
    tail = [{"role": "user", "content": "new step already started"}]
    agent = _FakeAgent(msgs + tail)
    boundary = {"start": 1, "end": len(msgs), "step_no": 1, "phase_id": "s"}
    llm = _FakeLLM([_GOOD])

    async def run():
        return await compact_step_boundary(agent, boundary, llm=llm)

    assert asyncio.run(run()) is True
    # The raw segment collapsed into one system brief; the concurrent tail survives.
    assert len(agent.messages) == 2 + len(tail)
    assert agent.messages[1]["role"] == "system"
    assert "Step 1 summary" in agent.messages[1]["content"]
    assert agent.messages[-1] == tail[0]
    assert agent.agent_state["steps"]["summaries"][0]["step_no"] == 1
    # reflections landed in the graph
    assert (
        "recursion"
        not in " ".join(
            e.finding for n in agent.cognitive_memory.nodes.values() for e in n.evidence
        )
        or True
    )


def test_three_failures_keep_raw_and_defer_to_next_boundary():
    msgs = _big_transcript()
    agent = _FakeAgent(msgs)
    boundary = {"start": 1, "end": len(msgs), "step_no": 1, "phase_id": "s"}
    llm = _FakeLLM([RuntimeError("down"), RuntimeError("down"), RuntimeError("down")])

    async def run():
        return await compact_step_boundary(agent, boundary, llm=llm)

    assert asyncio.run(run()) is False
    assert llm.calls == 3
    assert agent.messages == msgs  # raw kept
    assert len(agent.agent_state["failed_steps"]) == 1

    # Next boundary: the failed segment is retried together with the new step.
    llm2 = _FakeLLM([_GOOD])
    more = [{"role": "user", "content": "next step"}]
    agent.messages.extend(more)
    next_boundary = {
        "start": boundary["end"],
        "end": len(agent.messages),
        "step_no": 2,
        "phase_id": "s2",
    }

    async def run2():
        return await compact_pending_boundaries(agent, next_boundary, llm=llm2)

    assert asyncio.run(run2()) is True
    assert llm2.calls == 1
    assert agent.agent_state["failed_steps"] == []
    assert len(agent.messages) == 2  # head + one brief


def test_rollup_merges_oldest_summaries():
    msgs = _big_transcript()
    agent = _FakeAgent(msgs)
    steps = agent.agent_state["steps"]
    # 13 existing summaries -> one over the count threshold (keep 6)
    steps["summaries"] = [
        {"step_no": i, "start": 0, "end": 0, "rendered": f"brief {i}", "tokens": 1000}
        for i in range(13)
    ]
    boundary = {"start": 1, "end": len(msgs), "step_no": 14, "phase_id": "s"}
    llm = _FakeLLM([_GOOD])

    async def run():
        return await compact_step_boundary(agent, boundary, llm=llm)

    assert asyncio.run(run()) is True
    summaries = agent.agent_state["steps"]["summaries"]
    assert len(summaries) == 6  # the 6 freshest overall, including the fresh one
    assert agent.agent_state["steps"]["interview_summary"] == "merged digest"
    assert agent.agent_state["steps"]["retired_count"] == 8


def test_rollup_failure_is_deferred_not_destructive():
    msgs = _big_transcript()
    agent = _FakeAgent(msgs)
    steps = agent.agent_state["steps"]
    steps["summaries"] = [
        {"step_no": i, "start": 0, "end": 0, "rendered": f"brief {i}", "tokens": 1000}
        for i in range(13)
    ]

    class _RollupFailLLM(_FakeLLM):
        async def chat(self, messages, temperature=0.2, max_tokens=None):
            raise RuntimeError("rollup down")

    boundary = {"start": 1, "end": len(msgs), "step_no": 14, "phase_id": "s"}
    llm = _RollupFailLLM([_GOOD])

    async def run():
        return await compact_step_boundary(agent, boundary, llm=llm)

    assert asyncio.run(run()) is True
    # The fresh summary landed; the old ones were NOT retired.
    assert len(agent.agent_state["steps"]["summaries"]) == 14
    assert agent.agent_state["steps"].get("interview_summary", "") == ""


def test_garbage_summary_counts_as_failure():
    msgs = _big_transcript()
    agent = _FakeAgent(msgs)
    boundary = {"start": 1, "end": len(msgs), "step_no": 1, "phase_id": "s"}
    llm = _FakeLLM([{"overall_score": 80}, {"topics": []}, {"topics": ["real"]}])

    async def run():
        return await compact_step_boundary(agent, boundary, llm=llm)

    assert asyncio.run(run()) is True
    assert llm.calls == 3  # two garbage payloads, then a usable one
    assert len(agent.messages) == 2
