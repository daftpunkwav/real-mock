"""Platform Agent contract: JSON extraction, tool invocation, event emit, loop propagation.

Pins the single-source semantics shared by the resume and records domains:
canonical ``{"error", "tool", "message"}`` observations, business-error
propagation through the loop (never disguised as model observations), and
non-breaking event delivery.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from realmock.platform.capabilities.ai.agent import emit_agent_event, run_agent_loop
from realmock.platform.capabilities.ai.agent.tools import ToolBundle, ToolSpec, invoke_with_timeout
from realmock.platform.capabilities.ai.llm.json_extract import (
    extract_json_object,
    iter_balanced_objects,
    truncate_chunk,
)
from realmock.platform.core.errors import ApiBusinessError, raise_error


def _spec(name: str, handler, *, timeout_seconds: float | None = None) -> ToolSpec:
    return ToolSpec(
        name=name,
        description="test tool",
        parameters={},
        handler=handler,
        timeout_seconds=timeout_seconds,
    )


async def _ok_handler(args: dict) -> str:
    del args
    return '{"ok": true}'


def test_extract_json_object_recovers_noisy_and_key_richest() -> None:
    assert extract_json_object('{"a": 1}') == {"a": 1}
    assert extract_json_object("```json\n{\"a\": 1}\n```") == {"a": 1}
    noisy = '{"draft": 1} middle {"score": 5, "headline": "full"} end'
    assert extract_json_object(noisy) == {"score": 5, "headline": "full"}
    assert extract_json_object("") is None
    assert extract_json_object(None) is None
    assert extract_json_object("no braces at all") is None


def test_iter_balanced_objects_ignores_braces_in_strings_and_caps() -> None:
    text = 'noise {"narrative": "has {braces} inside", "score": 1} tail'
    assert list(iter_balanced_objects(text)) == [
        '{"narrative": "has {braces} inside", "score": 1}'
    ]
    many = " ".join(['{"a": 1}' for _ in range(300)])
    assert len(list(iter_balanced_objects(many))) == 200


def test_truncate_chunk_marks_omission() -> None:
    assert truncate_chunk("short", limit=100) == "short"
    clipped = truncate_chunk("y" * 1000, limit=200)
    assert len(clipped) < 1000
    assert "original 1000 chars" in clipped


async def test_invoke_with_timeout_success_shape() -> None:
    bundle = ToolBundle()
    bundle.add(_spec("lookup", _ok_handler))
    raw, status = await _invoke(bundle, "lookup", {}, timeout=5.0)
    assert status == "done"
    assert json.loads(raw) == {"ok": True}


async def test_invoke_with_timeout_maps_timeout_to_canonical_error() -> None:
    async def _slow(args: dict) -> str:
        del args
        await asyncio.sleep(5.0)
        return "late"  # pragma: no cover

    bundle = ToolBundle()
    bundle.add(_spec("slow", _slow))
    raw, status = await _invoke(bundle, "slow", {"q": "x"}, timeout=0.05)
    assert status == "error"
    payload = json.loads(raw)
    assert payload["error"] == "timeout"
    assert payload["tool"] == "slow"
    assert "exceeded" in payload["message"]
    assert payload["args"] == '{"q": "x"}'
    assert "Narrow the arguments" in payload["hint"]


async def test_invoke_with_timeout_maps_failure_to_canonical_error() -> None:
    async def _boom(args: dict) -> str:
        del args
        raise RuntimeError("boom")

    bundle = ToolBundle()
    bundle.add(_spec("broken", _boom))
    raw, status = await _invoke(bundle, "broken", {}, timeout=5.0)
    assert status == "error"
    payload = json.loads(raw)
    assert payload["error"] == "tool_failed"
    assert payload["tool"] == "broken"
    assert "boom" in payload["message"]
    assert payload["args"] == "{}"
    assert "hint" not in payload, "unknown failure classes carry no invented hint"


async def test_invoke_with_timeout_classifies_provider_error_hints() -> None:
    """Known provider failure classes carry an actionable hint; none are retried."""
    cases = [
        ("HTTP 404: Not Found", "Target not found"),
        ("409 Conflict: empty repository", "empty repository"),
        ("rate limit exceeded (429)", "Quota or access limited"),
    ]
    for message, expected_hint in cases:
        calls: list[int] = []

        async def _fail(args: dict, _message: str = message) -> str:
            del args
            calls.append(1)
            raise RuntimeError(_message)

        bundle = ToolBundle()
        bundle.add(_spec("target", _fail))
        raw, status = await _invoke(bundle, "target", {"id": "x"}, timeout=5.0)
        assert status == "error", message
        payload = json.loads(raw)
        assert payload["error"] == "tool_failed", message
        assert expected_hint in payload["hint"], message
        assert len(calls) == 1, "provider rejections are never retried here"


async def test_invoke_with_timeout_truncates_args_echo() -> None:
    """The echoed call arguments in an error observation are capped at 400 chars."""
    async def _boom(args: dict) -> str:
        del args
        raise RuntimeError("kaboom")

    bundle = ToolBundle()
    bundle.add(_spec("wide", _boom))
    raw, status = await _invoke(bundle, "wide", {"query": "y" * 5000}, timeout=5.0)
    assert status == "error"
    payload = json.loads(raw)
    assert len(payload["args"]) == 400
    assert payload["args"].startswith('{"query": "yyy')


async def test_invoke_with_timeout_falls_back_to_declared_spec_timeout() -> None:
    """No explicit timeout: the spec's reference value applies, then the default."""

    async def _slow(args: dict) -> str:
        del args
        await asyncio.sleep(5.0)
        return "late"  # pragma: no cover

    bundle = ToolBundle()
    bundle.add(_spec("slowish", _slow, timeout_seconds=0.05))
    raw, status = await invoke_with_timeout(bundle, "slowish", {})
    assert status == "error"
    assert "exceeded 0s" in json.loads(raw)["message"]

    # A tool without a declared timeout falls back to the platform default
    # (asserted indirectly: a fast handler still succeeds).
    bundle.add(_spec("plain", _ok_handler))
    raw2, status2 = await invoke_with_timeout(bundle, "plain", {})
    assert status2 == "done"
    assert json.loads(raw2) == {"ok": True}


async def test_invoke_with_timeout_retries_transient_connection_error_once() -> None:
    calls: list[int] = []

    async def _flaky(args: dict) -> str:
        del args
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionResetError("peer reset")
        return json.dumps({"ok": True})

    bundle = ToolBundle()
    bundle.add(_spec("flaky", _flaky))
    raw, status = await invoke_with_timeout(bundle, "flaky", {}, timeout=5.0)
    assert status == "done"
    assert len(calls) == 2, "exactly one connection retry"

    calls.clear()

    async def _always_down(args: dict) -> str:
        del args
        calls.append(1)
        raise ConnectionResetError("peer reset")

    bundle.add(_spec("down", _always_down))
    raw2, status2 = await invoke_with_timeout(bundle, "down", {}, timeout=5.0)
    assert status2 == "error"
    payload = json.loads(raw2)
    assert payload["error"] == "tool_failed"
    assert "Transient network failure" in payload["hint"]
    assert len(calls) == 2, "one initial attempt plus exactly one retry"


async def test_invoke_with_timeout_reraises_business_error() -> None:
    async def _denied(args: dict) -> str:
        del args
        raise_error("A1005")

    bundle = ToolBundle()
    bundle.add(_spec("guarded", _denied))
    with pytest.raises(ApiBusinessError) as exc_info:
        await _invoke(bundle, "guarded", {}, timeout=5.0)
    assert exc_info.value.error_code == "A1005"


async def _invoke(bundle, name: str, args: dict, *, timeout: float):
    from realmock.platform.capabilities.ai.agent.tools import invoke_with_timeout

    return await invoke_with_timeout(bundle, name, args, timeout=timeout)


async def test_emit_agent_event_supports_sync_async_and_none() -> None:
    seen: list[dict] = []
    await emit_agent_event(None, {"type": "ping"})
    await emit_agent_event(seen.append, {"type": "sync"})  # type: ignore[arg-type]

    async def _async_cb(event: dict) -> None:
        seen.append(event)

    await emit_agent_event(_async_cb, {"type": "async"})
    assert [e["type"] for e in seen] == ["sync", "async"]


async def test_emit_agent_event_never_raises() -> None:
    def _bad(event: dict):
        del event
        raise RuntimeError("ui exploded")

    await emit_agent_event(_bad, {"type": "tool_step"})  # must not raise


class _ToolCallLLM:
    """Minimal fake: first round calls a tool, then answers (unused on raise)."""

    def __init__(self) -> None:
        self.calls = 0

    async def chat_message(self, messages, temperature=0.7, tools=None, **kwargs):
        del messages, temperature, tools, kwargs
        self.calls += 1
        if self.calls == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "function": {"name": "guarded", "arguments": "{}"}}
                ],
            }
        return {"role": "assistant", "content": "unreached", "tool_calls": None}


async def test_loop_propagates_business_error_from_execute() -> None:
    async def execute(name: str, args: dict) -> str:
        del name, args
        raise_error("A1005")

    with pytest.raises(ApiBusinessError) as exc_info:
        await run_agent_loop(
            _ToolCallLLM(),
            [{"role": "user", "content": "hi"}],
            tools=[{"type": "function", "function": {"name": "guarded"}}],
            execute=execute,
            max_rounds=3,
        )
    assert exc_info.value.error_code == "A1005"


async def test_loop_still_converts_unexpected_tool_errors_to_observations() -> None:
    async def execute(name: str, args: dict) -> str:
        del name, args
        raise RuntimeError("flaky tool")

    llm = _ToolCallLLM()
    result = await run_agent_loop(
        llm,
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "flaky"}}],
        execute=execute,
        max_rounds=1,
    )
    assert result.tool_used is True
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    assert tool_msgs and "Tool execution failed" in tool_msgs[0]["content"]
