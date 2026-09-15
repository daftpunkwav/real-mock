"""Transcript summarization tests for apps/api/src/realmock/platform/capabilities/ai/context/summarize.py.

Covers: provenance/previous-summary/transcript/usage helpers, _summarize_transcript
overflow/empty/error paths and compact_with_summary threshold/cooldown/force/report branches.

Conventions: no real network (LLM faked via _FakeLLM); asyncio_mode=auto.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from realmock.platform.capabilities.ai.agent.working_memory import WorkingMemory
from realmock.platform.capabilities.ai.context import summarize as sum_mod
from realmock.platform.capabilities.ai.context.options import CompactionOptions
from realmock.platform.capabilities.ai.llm.usage import UsageAccumulator



def test_provenance_roundtrip_and_clamps() -> None:
    t = sum_mod.format_provenance(
        version=0, backup_session_id=9, fork_point=-3, focus="f" * 100,
        before=-1, after=5, base=2,
    )
    assert t.startswith("[provenance v=1 backup_session=9 fork_point=0 focus=")
    parsed = sum_mod.parse_provenance(f"notes\n{t}")
    assert parsed["v"] == 1 and parsed["backup_session"] == 9
    assert parsed["fork_point"] == 0 and parsed["base"] == 2
    assert sum_mod.parse_provenance("no trailer") == {}
    assert "v" not in sum_mod.parse_provenance("x [provenance v=abc before=1]")
    assert "before" in sum_mod.parse_provenance("x [provenance v=1 before=2]")

    class _Boom:
        __bool__ = lambda self: True  # noqa: E731
        def __str__(self) -> str:
            raise RuntimeError("boom")

    assert sum_mod.parse_provenance(_Boom()) == {}  # type: ignore[arg-type]
    assert sum_mod.strip_provenance(f"body\n{t}") == "body"
    assert sum_mod.strip_provenance("plain") == "plain"


def test_previous_summary_helpers() -> None:
    sys_msgs = [
        {"role": "system", "content": "rules"},
        {"role": "system", "content": "[Session summary] old\n[provenance v=3 base=4]"},
    ]
    assert sum_mod._previous_summary_text(sys_msgs) == "old"
    assert sum_mod._previous_summary_text([{"role": "system", "content": "x"}]) == ""
    kept = sum_mod._without_prior_summaries(sys_msgs)
    assert [m["content"] for m in kept] == ["rules"]
    tracked = [
        {"role": "system", "content": "rules"},
        {"role": "system", "content": "[Conversation Minutes] old\n[provenance v=3 base=4]"},
    ]
    assert sum_mod._previous_summary_base(tracked) == 4
    assert sum_mod._previous_summary_version(tracked) == 3
    assert sum_mod._previous_summary_base([{"role": "system", "content": "x"}]) is None
    assert sum_mod._previous_summary_version([{"role": "system", "content": "x"}]) == 0


def test_transcript_lines_images_and_clips() -> None:
    lines = sum_mod._transcript_lines([
        {"role": "user", "content": [{"image_url": {"url": "u"}}]},
        {"role": "user", "content": [{"text": "hi"}, {"image_url": {"url": "u"}}]},
        {"role": "user", "content": ""},
        {"role": "user", "content": "y" * 500},
    ])
    assert lines[0].endswith("[1 image(s) shared, content not textual]")
    assert lines[1].endswith("[+1 image(s)]")
    assert len(lines) == 3
    assert lines[2].endswith("…")
    assert sum_mod._count_images("x") == 0
    assert sum_mod._count_images([{"image_url": "u"}, {"text": "t"}]) == 1


def test_usage_snapshot_and_delta() -> None:
    llm = SimpleNamespace(usage=UsageAccumulator(prompt_tokens=3, completion_tokens=1))
    assert sum_mod._usage_snapshot(llm)["prompt_tokens"] == 3
    assert sum_mod._usage_snapshot(SimpleNamespace()) == {}
    bad = SimpleNamespace(usage=SimpleNamespace(to_dict=lambda: (_ for _ in ()).throw(RuntimeError("x"))))
    assert sum_mod._usage_snapshot(bad) == {}
    odd = SimpleNamespace(usage=SimpleNamespace(to_dict=lambda: {"a": 1, "b": "x"}))
    assert sum_mod._usage_snapshot(odd) == {"a": 1}
    assert sum_mod._usage_delta(llm, {"prompt_tokens": 1, "gone": 5}) == {
        "prompt_tokens": 2, "completion_tokens": 1,
    }


class _FakeLLM:
    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[tuple[Any, Any]] = []
        self.usage = UsageAccumulator()

    async def chat(self, messages: Any, **kw: Any) -> str:
        self.calls.append((messages, kw))
        self.usage.requests += 1
        self.usage.prompt_tokens += 10
        self.usage.completion_tokens += 5
        item = self.script.pop(0) if self.script else "S"
        if isinstance(item, Exception):
            raise item
        return item


def _long_messages(n: int, size: int = 150) -> list[dict[str, Any]]:
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i} " + "w" * size}
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_summarize_transcript_overflow_folds_earliest_by_count() -> None:
    llm = _FakeLLM(["S"] * 6)
    report: dict[str, Any] = {}
    out = await sum_mod._summarize_transcript(
        llm, "OLD", _long_messages(400, 20), CompactionOptions(),
        prefix_blocks=["SYS"], report=report,
    )
    assert out == "S"
    assert len(llm.calls) == 6  # 7 chunks → earliest folded, max 6 calls
    first_prompt = llm.calls[0][0][0]["content"]
    assert "Earliest 60 conversation snippets folded by count only" in first_prompt
    assert "OLD" in first_prompt  # prior chains forward
    assert llm.calls[0][1]["system"] == "SYS"
    assert report["prompt_tokens"] == 60
    assert report["completion_tokens"] == 30
    assert report["latency_ms"] > 0


@pytest.mark.asyncio
async def test_summarize_transcript_empty_summary_breaks_and_focus() -> None:
    llm = _FakeLLM([""])
    out = await sum_mod._summarize_transcript(
        llm, "PRIOR", _long_messages(3, 10), CompactionOptions(directive="FOCUS"),
    )
    assert out == ""  # empty model reply clears the running summary and stops chaining
    assert "FOCUS" in llm.calls[0][0][0]["content"]
    llm2 = _FakeLLM(["S2"])
    out2 = await sum_mod._summarize_transcript(
        llm2, "", _long_messages(3, 10), CompactionOptions(), default_focus="DF",
    )
    assert out2 == "S2"
    assert "DF" in llm2.calls[0][0][0]["content"]


@pytest.mark.asyncio
async def test_summarize_transcript_report_errors_swallowed() -> None:
    class _GetBoom(dict):  # type: ignore[type-arg]
        def get(self, key: Any, default: Any = None) -> Any:  # type: ignore[override]
            raise RuntimeError("boom")

    llm = _FakeLLM(["S"])
    out = await sum_mod._summarize_transcript(
        llm, "", _long_messages(3, 10), CompactionOptions(), report=_GetBoom(),
    )
    assert out == "S"


@pytest.mark.asyncio
async def test_compact_below_threshold_unchanged() -> None:
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    llm = _FakeLLM(["S"])
    assert await sum_mod.compact_with_summary(msgs, 100000, llm=llm) == msgs
    assert llm.calls == []
    assert await sum_mod.compact_with_summary(msgs, 100000, threshold=5, llm=llm) == msgs


@pytest.mark.asyncio
async def test_compact_cooldown_skips_refold() -> None:
    sys_sum = {
        "role": "system",
        "content": "[Conversation Minutes] old notes " + "n" * 200 + "\n"
        + sum_mod.format_provenance(version=1, before=100, after=60, base=2),
    }
    msgs = [sys_sum, {"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    llm = _FakeLLM(["S"])
    out = await sum_mod.compact_with_summary(msgs, 100, llm=llm)
    assert out == msgs  # 0 fresh turns since base=2 and window not urgent
    assert llm.calls == []


@pytest.mark.asyncio
async def test_compact_tiny_omitted_not_worth_folding() -> None:
    msgs = [{"role": "system", "content": "s"}] + [
        {"role": "user", "content": "hi"} for _ in range(6)
    ]
    llm = _FakeLLM(["S"])
    out = await sum_mod.compact_with_summary(msgs, 100, llm=llm, keep_recent=2)
    assert out == msgs
    assert llm.calls == []


@pytest.mark.asyncio
async def test_compact_keep_from_invalid_pins_to_zero() -> None:
    msgs = [{"role": "system", "content": "s"}] + _long_messages(4, 60)
    llm = _FakeLLM(["NOTE"])
    report: dict[str, Any] = {}
    out = await sum_mod.compact_with_summary(
        msgs, 100, llm=llm, force=True, keep_from="oops", report=report,  # type: ignore[arg-type]
    )
    # Invalid pin → pinned=0 → whole history stays verbatim, nothing to omit.
    assert out == msgs
    assert llm.calls == []
    assert report["kept_from"] == 1


@pytest.mark.asyncio
async def test_compact_report_kept_from_fallback_to_length() -> None:
    # Two stale tool rounds rebuild into fresh dicts; with keep=2 the verbatim
    # head is the second rebuild: identity and equality scans both miss.
    msgs = [
        {"role": "assistant", "content": "first tool answer", "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "r1"},
        {"role": "assistant", "content": "second tool answer", "tool_calls": [{"id": "c2"}]},
        {"role": "tool", "tool_call_id": "c2", "content": "r2"},
        {"role": "user", "content": "plain follow up"},
    ]
    report: dict[str, Any] = {}
    out = await sum_mod.compact_with_summary(msgs, 100, llm=None, force=True, report=report)
    assert report["kept_from"] == len(msgs)
    assert len(out) == 3  # rule digest block + 2 verbatim tail messages


@pytest.mark.asyncio
async def test_compact_report_kept_from_equality_hit() -> None:
    # The rebuilt head is a fresh dict, but an identical plain assistant turn
    # exists: identity misses, equality hits and pins its index.
    msgs = [
        {"role": "assistant", "content": "SAME"},
        {"role": "assistant", "content": "SAME", "tool_calls": [{"id": "c"}]},
        {"role": "tool", "tool_call_id": "c", "content": "r"},
        {"role": "user", "content": "next"},
    ]
    report: dict[str, Any] = {}
    out = await sum_mod.compact_with_summary(msgs, 100, llm=None, force=True, report=report)
    assert report["kept_from"] == 0
    assert len(out) == 3


@pytest.mark.asyncio
async def test_compact_report_exception_swallowed() -> None:
    class _EqBoom(dict):  # type: ignore[type-arg]
        def __eq__(self, other: Any) -> bool:
            raise RuntimeError("boom")

    hostile = _EqBoom(role="user", content="hostile text here")
    msgs = [
        {"role": "assistant", "content": "first tool answer", "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "r1"},
        {"role": "assistant", "content": "second tool answer", "tool_calls": [{"id": "c2"}]},
        {"role": "tool", "tool_call_id": "c2", "content": "r2"},
        hostile,
    ]
    report: dict[str, Any] = {}
    out = await sum_mod.compact_with_summary(msgs, 100, llm=None, force=True, report=report)
    assert "kept_from" not in report  # equality scan hit the hostile entry → swallowed
    assert any(str(m.get("content")).startswith("[Context compression]") for m in out)


@pytest.mark.asyncio
async def test_compact_llm_success_with_memory_and_provenance() -> None:
    mem = WorkingMemory()
    llm = _FakeLLM(["NOTE"])
    report: dict[str, Any] = {}
    msgs = [{"role": "system", "content": "rules"}] + _long_messages(6, 60)
    out = await sum_mod.compact_with_summary(
        msgs, 100, memory=mem, llm=llm, force=True, report=report,
        provenance={"backup_session_id": 9, "fork_point": 2},
    )
    block = next(m for m in out if str(m.get("content")).startswith("[Conversation Minutes]"))
    assert "NOTE" in str(block["content"])
    assert "backup_session=9 fork_point=2" in str(block["content"])
    assert "base=2" in str(block["content"])
    assert mem.notes and "Earlier dialogue summary" in mem.notes[0]
    assert report["kept_from"] == 5
    assert report["prompt_tokens"] == 10


@pytest.mark.asyncio
async def test_compact_growing_summary_keeps_original() -> None:
    msgs = [{"role": "system", "content": "s"}] + _long_messages(10, 130)
    llm = _FakeLLM(["N" * 2000])  # summary costs more than the fold saves
    out = await sum_mod.compact_with_summary(msgs, 100, llm=llm, keep_recent=4)
    assert out == msgs
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_compact_force_failure_raises_but_auto_falls_back() -> None:
    msgs = [{"role": "system", "content": "s"}] + _long_messages(12, 150)
    with pytest.raises(RuntimeError, match="down"):
        await sum_mod.compact_with_summary(
            msgs, 100, llm=_FakeLLM([RuntimeError("down")]), force=True, keep_recent=4,
        )
    out = await sum_mod.compact_with_summary(
        msgs, 100, llm=_FakeLLM([RuntimeError("down")]), keep_recent=4,
    )
    body = next(m for m in out if str(m.get("content")).startswith("[Context compression]"))
    assert "12" not in str(body) or "omitted" in str(body)
    assert "User demands" in str(body)
    assert "[provenance" in str(body)
