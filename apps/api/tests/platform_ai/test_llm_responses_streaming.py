"""Responses-protocol streaming: round assembler, reasoning extraction, dispatch.

Contract:
- ``_ResponsesRoundAssembler`` turns responses SSE deltas into reasoning/text
  increments plus buffered function calls; ``response.completed`` is the
  authoritative terminal snapshot, buffers are only the fallback;
- ``parse_sse_event`` surfaces reasoning deltas for the plain text stream;
- ``extract_reasoning`` concatenates reasoning-summary items non-streaming;
- ``chat_message_stream`` no longer rejects the responses protocol.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from realmock.platform.capabilities.ai.llm.client.assemblers import _ResponsesRoundAssembler
from realmock.platform.capabilities.ai.llm.client.response_extract import (
    extract_reasoning,
    parse_sse_event,
)


def _completed(output: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "response.completed", "response": {"output": output, "usage": {}}}


def test_assembler_streams_reasoning_and_text() -> None:
    a = _ResponsesRoundAssembler()
    reasoning = a.feed({"type": "response.reasoning_summary_text.delta", "delta": "think A"})
    reasoning += a.feed({"type": "response.reasoning_text.delta", "delta": " think B"})
    assert reasoning == "think A think B"
    assert a.feed({"type": "response.output_text.delta", "delta": "Hello "}) == ""
    assert a.feed({"type": "response.output_text.delta", "delta": "world"}) == ""
    assert a.drain_content() == "Hello world"
    assert a.drain_content() == ""


def test_assembler_buffers_tool_calls_from_deltas() -> None:
    a = _ResponsesRoundAssembler()
    a.feed({"type": "response.output_item.added", "item": {
        "type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "resume_get_section",
    }})
    a.feed({"type": "response.function_call_arguments.delta", "item_id": "fc_1", "delta": '{"sec'})
    a.feed({"type": "response.function_call_arguments.delta", "item_id": "fc_1", "delta": 'tion": "edu"}'})

    msg = a.message()
    assert msg["role"] == "assistant" and msg["content"] is None
    assert msg["tool_calls"][0]["id"] == "call_1"
    assert msg["tool_calls"][0]["function"]["name"] == "resume_get_section"
    assert msg["tool_calls"][0]["function"]["arguments"] == '{"section": "edu"}'


def test_completed_snapshot_is_authoritative() -> None:
    a = _ResponsesRoundAssembler()
    a.feed({"type": "response.output_text.delta", "delta": "partial"})
    a.feed(_completed([
        {"type": "message", "content": [{"type": "output_text", "text": "final body"}]},
        {"type": "function_call", "id": "fc_9", "call_id": "call_9", "name": "t",
         "arguments": "{\"x\": 1}"},
    ]))
    msg = a.message()
    # The completed snapshot replaces delta-stitched buffers (no drift).
    assert msg["content"] == "final body"
    assert msg["tool_calls"][0]["id"] == "call_9"
    assert msg["tool_calls"][0]["function"]["arguments"] == "{\"x\": 1}"


def test_no_completed_event_falls_back_to_buffers() -> None:
    a = _ResponsesRoundAssembler()
    a.feed({"type": "response.output_text.delta", "delta": "kept"})
    assert a.message()["content"] == "kept"


def test_parse_sse_event_surfaces_reasoning() -> None:
    token, think = parse_sse_event(
        {"type": "response.reasoning_summary_text.delta", "delta": "hmm"}, "openai_responses"
    )
    assert token == "" and think == "hmm"
    token, think = parse_sse_event(
        {"type": "response.output_text.delta", "delta": "hi"}, "openai_responses"
    )
    assert token == "hi" and think == ""


def test_extract_reasoning_concatenates_summaries() -> None:
    data = {"output": [
        {"type": "reasoning", "summary": [{"type": "summary_text", "text": "a"}, {"text": "b"}]},
        {"type": "message", "content": []},
    ]}
    assert extract_reasoning(data, "openai_responses") == "ab"
    assert extract_reasoning({"output": [{"type": "message"}]}, "openai_responses") == ""


def test_stream_message_round_dispatches_responses_assembler(monkeypatch) -> None:
    """stream_message_round routes the responses protocol to the responses assembler."""
    from realmock.platform.capabilities.ai.llm.client import streaming as stream_mod

    seen: dict[str, Any] = {}

    class _FakeResp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        async def aiter_lines(self):
            yield 'data: {"type": "response.reasoning_summary_text.delta", "delta": "why"}'
            yield 'data: {"type": "response.output_text.delta", "delta": "answer"}'
            yield "data: [DONE]"

    class _FakeCtx:
        async def __aenter__(self):
            return _FakeResp()

        async def __aexit__(self, *exc):
            return False

    class _FakeClient:
        def stream(self, method, url, headers=None, json=None):
            seen["json"] = json
            return _FakeCtx()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class _Usage:
        def record_stream_event(self, event, protocol):
            return None

        def note_request_start(self):
            return None

        def note_response_meta(self, headers):
            return None

        def note_request_error(self, exc):
            return None

    monkeypatch.setattr(stream_mod, "make_pinned_async_client", lambda *a, **k: _FakeClient())
    client = SimpleNamespace(usage=_Usage(), extra_headers=None)
    events = asyncio.run(_gather(stream_mod.stream_message_round(
        client, "https://api.example.com", "openai_responses", "key", "https://api.example.com/responses", {},
    )))
    reasoning = [e for e in events if e["type"] == "reasoning"]
    text = [e for e in events if e["type"] == "text"]
    assert reasoning and reasoning[0]["text"] == "why"
    assert text and text[0]["text"] == "answer"
    assert events[-1]["type"] == "message"


async def _gather(agen):
    return [e async for e in agen]
