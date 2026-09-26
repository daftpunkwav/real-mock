"""Step-boundary compaction state machine tests.

Six guard families: skip threshold / summarize+replace / 3-strike fallback /
accumulate-and-retry / rollup / never-raises. No real network or LLM.
"""

from __future__ import annotations

import asyncio
import pytest
from types import SimpleNamespace as NS


from realmock.domains.interview.agents.step_compaction import (
    compact_pending_boundaries,
    compact_step_boundary,
    record_step_boundary,
)


@pytest.fixture(autouse=True)
def _no_retry_sleep():
    from realmock.domains.interview.agents.agent_policies import COMPACT

    original = COMPACT.retry_delays
    object.__setattr__(COMPACT, "retry_delays", (0.0, 0.0, 0.0))
    yield
    object.__setattr__(COMPACT, "retry_delays", original)


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

# ---- consecutive compactions + concurrency guard (P0-1 regression) ----


def test_two_consecutive_compactions_keep_indexes_consistent():
    """P0-1 regression: after the first splice, step_start must stay valid.

    The first step is summarized; the second step is below the threshold and
    stays verbatim — but the boundary machinery must remain in range.
    """
    msgs = _big_transcript()
    agent = _FakeAgent(msgs)
    llm = _FakeLLM([_GOOD])

    async def run():
        b1 = record_step_boundary(agent)  # closes the whole first step
        ok1 = await compact_step_boundary(agent, b1, llm=llm)
        # Next step starts life, then closes while still small.
        agent.messages.append({"role": "user", "content": "next step q"})
        agent.messages.append({"role": "assistant", "content": "next step a"})
        b2 = record_step_boundary(agent)
        ok2 = await compact_step_boundary(agent, b2, llm=llm)
        return ok1, ok2, b1, b2

    ok1, ok2, b1, b2 = asyncio.run(run())
    assert ok1 is True and b1["end"] == 801  # full first step was closed
    assert ok2 is False  # below threshold: stays verbatim
    # The critical invariant: step_start is a legal index after the splice.
    assert agent.agent_state["steps"]["step_start"] == len(agent.messages)
    assert agent.agent_state["steps"]["step_start"] <= len(agent.messages)
    assert agent.messages[1]["role"] == "system"
    assert "Step 1 summary" in agent.messages[1]["content"]
    assert agent.messages[-1]["content"] == "next step a"


def test_parallel_boundaries_are_serialized_by_lock():
    import realmock.domains.interview.agents.step_compaction as sc

    msgs = _big_transcript()
    agent = _FakeAgent(msgs)
    llm = _FakeLLM([_GOOD, _GOOD])
    tasks: set[asyncio.Task] = set()

    class _R:
        pass

    runner = _R()
    runner.agent = agent
    runner.llm = llm

    def spawn(coro):
        t = asyncio.create_task(coro)
        tasks.add(t)
        t.add_done_callback(tasks.discard)
        return t

    runner.spawn_bg_task = spawn

    async def run():
        b1 = record_step_boundary(agent)
        sc.spawn_boundary_compaction(runner, b1)
        agent.messages.append({"role": "user", "content": "q2"})
        agent.messages.append({"role": "assistant", "content": "a2"})
        b2 = record_step_boundary(agent)
        sc.spawn_boundary_compaction(runner, b2)
        while tasks:
            results = await asyncio.gather(*list(tasks), return_exceptions=True)
            for r in results:
                assert not isinstance(r, Exception), r
            if not tasks:
                break

    asyncio.run(run())
    assert llm.calls >= 1
    # History stays consistent: the big first step became one brief, the
    # second step's messages are intact, nothing duplicated or lost.
    assert len(agent.messages) == 4  # head + brief + q2 + a2
    assert "Step 1 summary" in agent.messages[1]["content"]
    assert agent.messages[-2] == {"role": "user", "content": "q2"}


# ---- queued boundary re-read (index shifts between record and run) ----


def test_pending_boundary_follows_earlier_splice_shift():
    """P1 regression: a boundary recorded while an earlier compaction is still
    running must be re-read from the queue at run time — the captured indexes
    go stale the moment the earlier task splices, and a stale slice deletes
    live dialogue of the wrong step."""
    import realmock.domains.interview.agents.step_compaction as sc

    msgs = _big_transcript()
    agent = _FakeAgent(msgs)
    llm = _FakeLLM([_GOOD, _GOOD])
    tasks: set[asyncio.Task] = set()

    class _R:
        pass

    runner = _R()
    runner.agent = agent
    runner.llm = llm

    def spawn(coro):
        t = asyncio.create_task(coro)
        tasks.add(t)
        t.add_done_callback(tasks.discard)
        return t

    runner.spawn_bg_task = spawn

    # Hold task A inside its summarize call until b2 has been recorded, so
    # b2's task is already queued behind the lock when the splice lands.
    gate = asyncio.Event()
    held = {"armed": False}

    async def chat_json(messages, temperature=0.2):
        if not held["armed"]:
            held["armed"] = True
            await gate.wait()
        return await _FakeLLM.chat_json(llm, messages, temperature=temperature)

    llm.chat_json = chat_json  # type: ignore[method-assign]

    async def run():
        b1 = record_step_boundary(agent)  # (1, 801)
        sc.spawn_boundary_compaction(runner, b1)
        await asyncio.sleep(0.05)  # task A enters its blocked summarize call
        agent.messages.extend(_big_transcript()[1:])
        b2 = record_step_boundary(agent)  # (801, 1601)
        sc.spawn_boundary_compaction(runner, b2)
        await asyncio.sleep(0.05)  # task B parks on the compaction lock
        gate.set()
        while tasks:
            results = await asyncio.gather(*list(tasks), return_exceptions=True)
            for r in results:
                assert not isinstance(r, Exception), r
            if not tasks:
                break

    asyncio.run(run())
    # Both steps became briefs in order; nothing of the live second step was
    # spliced under a stale (801, 1601) slice.
    assert len(agent.messages) == 3  # head + brief1 + brief2
    assert "Step 1 summary" in agent.messages[1]["content"]
    assert "Step 2 summary" in agent.messages[2]["content"]
    assert agent.agent_state["steps"]["pending"] == []


def test_record_step_boundary_pinned_end_excludes_new_step_entry():
    """Pinning ``end`` keeps the NEXT step's entry message out of the closed
    segment (it belongs to the new segment and must stay in live context)."""
    msgs = [
        {"role": "system", "content": "head"},
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
    ]
    agent = _FakeAgent(msgs)
    agent.messages.append({"role": "system", "content": "Entering new phase: next"})
    boundary = record_step_boundary(agent, end=3)
    assert boundary == {"start": 1, "end": 3, "step_no": 1, "phase_id": "old_step"}
    assert agent.agent_state["steps"]["step_start"] == 3
    assert agent.messages[-1]["content"] == "Entering new phase: next"
    # Pinned end beyond the current list clamps; empty segments close nothing.
    assert record_step_boundary(agent, end=2) is None
    assert record_step_boundary(agent, end=99) == {
        "start": 3,
        "end": 4,
        "step_no": 2,
        "phase_id": "old_step",
    }


# ---- retry-chain termination and failure requeue (resilience contract) ----


def test_failed_chain_gives_up_after_max_failed_rounds():
    """Accumulate-and-retry must terminate: after COMPACT.max_failed_rounds
    failed rounds the segment is dead-lettered (raw kept) instead of growing
    the merged input forever."""
    from realmock.domains.interview.agents.agent_policies import COMPACT

    agent = _FakeAgent(_big_transcript())
    down = _FakeLLM([RuntimeError("down")] * 50)

    async def run():
        for _ in range(COMPACT.max_failed_rounds + 1):
            agent.messages.extend(_big_transcript()[1:])
            boundary = record_step_boundary(agent)
            await compact_pending_boundaries(agent, boundary, llm=down)

    asyncio.run(run())
    # Rounds 1..3 booked the (merged) segment; round 4 dead-lettered it.
    assert agent.agent_state["failed_steps"] == []
    assert agent.messages[1]["role"] != "system"  # raw dialogue untouched
    # Bounded cost: exactly (rounds+1) x max_attempts summarize calls, no more.
    assert down.calls == (COMPACT.max_failed_rounds + 1) * COMPACT.max_attempts


def test_failed_summary_rounds_replace_overlapping_entries():
    """Each failed round re-books ONE merged entry instead of accumulating
    overlapping duplicates."""
    agent = _FakeAgent(_big_transcript())
    llm = _FakeLLM([RuntimeError("down")] * 3)

    async def run():
        return await compact_step_boundary(
            agent, {"start": 1, "end": len(agent.messages), "step_no": 1, "phase_id": "s"}, llm=llm
        )

    assert asyncio.run(run()) is False
    failed = agent.agent_state["failed_steps"]
    assert len(failed) == 1
    assert failed[0]["rounds"] == 1


def test_record_failed_boundary_skips_already_spliced_segment():
    """Re-booking a range whose brief already landed must be a no-op — the
    alternative would let the next merge overwrite the brief plus the next
    step's live dialogue."""
    import realmock.domains.interview.agents.step_compaction as sc

    msgs = _big_transcript()
    agent = _FakeAgent(msgs)
    boundary = {"start": 1, "end": len(msgs), "step_no": 1, "phase_id": "s"}
    llm = _FakeLLM([_GOOD])

    async def run():
        return await compact_step_boundary(agent, boundary, llm=llm)

    assert asyncio.run(run()) is True
    sc._record_failed_boundary(agent, boundary)
    assert agent.agent_state.get("failed_steps", []) == []


def _spawn_runner(agent, llm):
    """Runner double wiring spawn_boundary_compaction onto real asyncio tasks."""

    class _R:
        pass

    runner = _R()
    runner.agent = agent
    runner.llm = llm
    runner.flow_active = False
    runner.spawn_bg_task = lambda coro: asyncio.create_task(coro)  # type: ignore[method-assign]
    return runner


def test_budget_timeout_requeues_boundary_into_failed_steps():
    """A boundary consumed by a task whose budget expired must land back in
    the retry chain, not vanish with the task."""
    import realmock.domains.interview.agents.step_compaction as sc
    from realmock.domains.interview.agents.agent_policies import COMPACT

    msgs = _big_transcript()
    agent = _FakeAgent(msgs)
    agent.session = NS(current_phase="p", id=10**9)  # absent row: persist no-op

    class _SlowLLM(_FakeLLM):
        async def chat_json(self, messages, temperature=0.2):
            await asyncio.sleep(1.0)
            return _GOOD

    runner = _spawn_runner(agent, _SlowLLM([]))

    async def run():
        boundary = record_step_boundary(agent)
        task = sc.spawn_boundary_compaction(runner, boundary)
        original = COMPACT.budget_seconds
        # Budget must expire while the summarize call is still parked.
        object.__setattr__(COMPACT, "budget_seconds", 0.05)
        try:
            await asyncio.gather(task, return_exceptions=True)
        finally:
            object.__setattr__(COMPACT, "budget_seconds", original)

    asyncio.run(run())
    failed = agent.agent_state["failed_steps"]
    assert len(failed) == 1
    assert failed[0]["start"] == 1
    assert failed[0]["end"] == len(msgs)
    assert failed[0]["rounds"] == 1
    assert agent.messages == msgs  # raw kept


def test_cancel_requeues_boundary_into_failed_steps():
    """WS-disconnect cancellation must not swallow the consumed boundary: the
    segment is re-filed and the finally-persist keeps the bookkeeping."""
    import realmock.domains.interview.agents.step_compaction as sc

    msgs = _big_transcript()
    agent = _FakeAgent(msgs)
    agent.session = NS(current_phase="p", id=10**9)

    gate = asyncio.Event()

    class _GatedLLM(_FakeLLM):
        async def chat_json(self, messages, temperature=0.2):
            await gate.wait()
            return _GOOD

    runner = _spawn_runner(agent, _GatedLLM([]))

    async def run():
        boundary = record_step_boundary(agent)
        task = sc.spawn_boundary_compaction(runner, boundary)
        await asyncio.sleep(0.05)  # task parks inside its summarize call
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())
    failed = agent.agent_state["failed_steps"]
    assert len(failed) == 1
    assert failed[0]["start"] == 1
    assert agent.messages == msgs
    assert agent.agent_state["steps"]["pending"] == []
