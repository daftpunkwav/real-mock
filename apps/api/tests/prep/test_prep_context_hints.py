"""Per-turn context hints ([Context usage] suffix) and dangling tool-pair pruning."""

from __future__ import annotations

import asyncio

from realmock.domains.prep.agents.agent import PrepAgent
from realmock.domains.prep.agents.context import (
    USAGE_HINT_MARKER,
    build_working_context,
)
from realmock.domains.prep.routes.chat import _prune_dangling_tool_tail
from realmock.platform.capabilities.ai.agent import WorkingMemory


class _FakeLLM:
    def __init__(self, context_window: int = 0):
        self.context_window = context_window

    async def chat(self, messages, **kwargs):  # pragma: no cover - not used below
        return ""


class _FakeSession:
    messages = "[]"
    resume_id = None
    target_company = ""
    token_usage = 0
    prompt_tokens = 0
    completion_tokens = 0
    cached_tokens = 0


class _FakeDB:
    def commit(self):
        pass

    def query(self, model):
        return _FakeQuery()


class _FakeQuery:
    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None


def _run(coro):
    return asyncio.run(coro)


def test_build_working_context_appends_usage_hint_tail() -> None:
    """The per-turn usage hint lands as the trailing system message."""
    messages = [
        {"role": "system", "content": "seed"},
        {"role": "user", "content": "hello"},
    ]
    out = _run(build_working_context(
        messages, 100_000, memory=WorkingMemory(), llm=None, reply_locale="en",
    ))
    assert out[-1]["role"] == "system"
    assert out[-1]["content"].startswith(USAGE_HINT_MARKER)
    assert "~" in out[-1]["content"] and "tokens" in out[-1]["content"]


def test_usage_hint_is_upserted_not_accumulated() -> None:
    """A second assembly replaces the previous usage block instead of stacking copies."""
    messages = [{"role": "user", "content": "hello"}]
    first = _run(build_working_context(
        messages, 100_000, memory=WorkingMemory(), llm=None, reply_locale="en",
    ))
    grown = [*first, {"role": "user", "content": "more input " * 200}]
    second = _run(build_working_context(
        grown, 100_000, memory=WorkingMemory(), llm=None, reply_locale="en",
    ))
    copies = [
        m for m in second
        if m.get("role") == "system"
        and isinstance(m.get("content"), str)
        and m["content"].startswith(USAGE_HINT_MARKER)
    ]
    assert len(copies) == 1
    assert second[-1]["content"].startswith(USAGE_HINT_MARKER)


def test_turn_tool_definitions_are_cache_stable() -> None:
    """The compact tool declaration carries no per-turn usage text, so the tools
    array (request head) stays byte-stable across turns for prompt caching."""
    agent = PrepAgent(_FakeSession(), _FakeLLM())  # type: ignore[arg-type]
    agent.messages = [{"role": "user", "content": "short"}]
    first = agent._tool_definitions("hi")
    agent.messages.append({"role": "assistant", "content": "grew " * 2000})
    second = agent._tool_definitions("hi")
    assert first == second
    compact = next(
        t for t in second if t.get("function", {}).get("name") == "compact_context"
    )
    assert "Current context usage" not in compact["function"]["description"]


# ── _prune_dangling_tool_tail: suffix cuts must leave a protocol-clean tail ────────────────


def _assistant(call_ids: list[str]) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": cid, "type": "function", "function": {"name": "t", "arguments": "{}"}}
            for cid in call_ids
        ],
    }


def _tool(call_id: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": "ok"}


def test_prune_keeps_complete_pairs() -> None:
    messages = [
        {"role": "user", "content": "q"},
        _assistant(["a", "b"]),
        _tool("a"),
        _tool("b"),
        {"role": "assistant", "content": "done"},
    ]
    assert _prune_dangling_tool_tail(messages) == messages


def test_prune_drops_orphan_tool_result() -> None:
    """Cut before the declaring assistant leaves an orphan tool result: dropped."""
    messages = [
        {"role": "user", "content": "q"},
        _tool("orphan"),
    ]
    pruned = _prune_dangling_tool_tail(messages)
    assert [m["role"] for m in pruned] == ["user"]


def test_prune_drops_incomplete_pair_group() -> None:
    """Cut between results of one assistant: the whole broken group goes."""
    messages = [
        {"role": "user", "content": "q"},
        _assistant(["a", "b"]),
        _tool("a"),
    ]
    pruned = _prune_dangling_tool_tail(messages)
    assert [m["role"] for m in pruned] == ["user"]


def test_prune_drops_trailing_toolless_assistant_with_calls() -> None:
    messages = [
        {"role": "user", "content": "q"},
        _assistant(["a"]),
        _tool("a"),
        _assistant(["b"]),
    ]
    pruned = _prune_dangling_tool_tail(messages)
    assert [m["role"] for m in pruned] == ["user", "assistant", "tool"]


def test_prune_keeps_earlier_pairs_while_fixing_tail() -> None:
    messages = [
        _assistant(["a"]),
        _tool("a"),
        _assistant(["b", "c"]),
        _tool("b"),
    ]
    pruned = _prune_dangling_tool_tail(messages)
    assert [m["role"] for m in pruned] == ["assistant", "tool"]


def test_prune_handles_empty_and_plain() -> None:
    assert _prune_dangling_tool_tail([]) == []
    plain = [{"role": "user", "content": "q"}]
    assert _prune_dangling_tool_tail(plain) == plain


def test_prune_tolerates_corrupt_tool_calls_shapes() -> None:
    """A non-list ``tool_calls`` must not crash pruning; the orphan result still goes,
    while the corrupt assistant row itself is left for its owner to fix."""
    messages = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": None, "tool_calls": "corrupt"},
        _tool("a"),
    ]
    pruned = _prune_dangling_tool_tail(messages)
    assert [m["role"] for m in pruned] == ["user", "assistant"]


def test_prune_drops_duplicate_id_orphan_after_interrupted_run() -> None:
    """A result id reused after a non-tool message is an orphan, not a pair completion."""
    messages = [
        _assistant(["a"]),
        _tool("a"),
        {"role": "user", "content": "next"},
        _tool("a"),
    ]
    pruned = _prune_dangling_tool_tail(messages)
    assert [m["role"] for m in pruned] == ["assistant", "tool", "user"]
