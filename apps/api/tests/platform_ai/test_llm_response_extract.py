"""Response extraction tests for apps/api/src/realmock/platform/capabilities/ai/llm/client/response_extract.py.

Covers: extract_text, extract_tool_calls, extract_reasoning and parse_sse_event
across OPENAI_CHAT, ANTHROPIC_MESSAGES and OPENAI_RESPONSES payloads.

Conventions: pure functions, no network; asyncio_mode=auto.
"""

from __future__ import annotations

from realmock.platform.capabilities.ai.llm.client.response_extract import (
    extract_reasoning,
    extract_text,
    extract_tool_calls,
    parse_sse_event,
)
from realmock.platform.core.constants import LLMProtocol

CHAT = LLMProtocol.OPENAI_CHAT
ANTH = LLMProtocol.ANTHROPIC_MESSAGES
RESP = LLMProtocol.OPENAI_RESPONSES


# ── extract_text ──


def test_extract_text_anthropic_str_content() -> None:
    assert extract_text({"content": "hello"}, ANTH) == "hello"


def test_extract_text_anthropic_list_text_only() -> None:
    data = {"content": [{"type": "text", "text": "a"}, {"type": "tool_use", "text": "x"}]}
    assert extract_text(data, ANTH) == "a"


def test_extract_text_anthropic_non_list_returns_empty() -> None:
    assert extract_text({"content": 123}, ANTH) == ""


def test_extract_text_anthropic_missing_content() -> None:
    assert extract_text({}, ANTH) == ""


def test_extract_text_responses_output_text() -> None:
    assert extract_text({"output_text": "hi"}, RESP) == "hi"


def test_extract_text_responses_output_message_list() -> None:
    data = {"output": [{"type": "message", "content": [{"text": "a"}, {"text": "b"}]}]}
    assert extract_text(data, RESP) == "ab"


def test_extract_text_responses_output_message_str_content() -> None:
    data = {"output": [{"type": "message", "content": "hello"}]}
    assert extract_text(data, RESP) == "hello"


def test_extract_text_responses_empty() -> None:
    assert extract_text({}, RESP) == ""
    assert extract_text({"output": [{"type": "reasoning"}]}, RESP) == ""


def test_extract_text_chat_string_content() -> None:
    data = {"choices": [{"message": {"content": "hello"}}]}
    assert extract_text(data, CHAT) == "hello"


def test_extract_text_chat_list_content() -> None:
    data = {"choices": [{"message": {"content": [{"text": "a"}, {"nope": 1}, "x"]}}]}
    assert extract_text(data, CHAT) == "a"


def test_extract_text_chat_reasoning_fallback() -> None:
    assert extract_text({"choices": [{"message": {"reasoning_content": "think"}}]}, CHAT) == "think"
    assert extract_text({"choices": [{"message": {"reasoning": "r2"}}]}, CHAT) == "r2"
    assert extract_text({"choices": [{"message": {"output_text": "o"}}]}, CHAT) == "o"


def test_extract_text_chat_empty_choices() -> None:
    assert extract_text({}, CHAT) == ""
    assert extract_text({"choices": []}, CHAT) == ""


def test_extract_text_chat_blank_content_falls_through() -> None:
    data = {"choices": [{"message": {"content": "   ", "reasoning_content": "rc"}}]}
    assert extract_text(data, CHAT) == "rc"


# ── extract_tool_calls ──


def test_extract_tool_calls_anthropic() -> None:
    data = {
        "content": [
            {"type": "tool_use", "id": "t1", "name": "lookup", "input": {"q": "x"}},
            {"type": "text", "text": "hi"},
            "not-a-dict",
        ]
    }
    calls = extract_tool_calls(data, ANTH)
    assert len(calls) == 1
    assert calls[0]["id"] == "t1"
    assert calls[0]["function"]["name"] == "lookup"
    assert '"q"' in calls[0]["function"]["arguments"]


def test_extract_tool_calls_anthropic_missing_fields() -> None:
    calls = extract_tool_calls({"content": [{"type": "tool_use"}]}, ANTH)
    assert calls[0]["id"] == ""
    assert calls[0]["function"]["name"] == ""


def test_extract_tool_calls_responses() -> None:
    data = {
        "output": [
            {"type": "function_call", "call_id": "c1", "name": "fn", "arguments": {"a": 1}},
            {"type": "message"},
            "x",
        ]
    }
    calls = extract_tool_calls(data, RESP)
    assert len(calls) == 1
    assert calls[0]["id"] == "c1"
    assert calls[0]["function"]["name"] == "fn"


def test_extract_tool_calls_responses_id_fallback() -> None:
    data = {"output": [{"type": "function_call", "id": "i2", "name": "g", "arguments": '{"b":2}'}]}
    calls = extract_tool_calls(data, RESP)
    assert calls[0]["id"] == "i2"
    assert calls[0]["function"]["arguments"] == '{"b":2}'


def test_extract_tool_calls_chat() -> None:
    tc = [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}]
    assert extract_tool_calls({"choices": [{"message": {"tool_calls": tc}}]}, CHAT) == tc
    assert extract_tool_calls({"choices": [{"message": {}}]}, CHAT) == []
    assert extract_tool_calls({}, CHAT) == []


# ── extract_reasoning ──


def test_extract_reasoning_anthropic() -> None:
    data = {"content": [{"type": "thinking", "thinking": "a"}, {"type": "text", "text": "b"}]}
    assert extract_reasoning(data, ANTH) == "a"


def test_extract_reasoning_anthropic_non_list() -> None:
    assert extract_reasoning({"content": "x"}, ANTH) == ""


def test_extract_reasoning_chat() -> None:
    assert extract_reasoning({"choices": [{"message": {"reasoning_content": "rc"}}]}, CHAT) == "rc"
    assert extract_reasoning({"choices": [{"message": {"reasoning": "r"}}]}, CHAT) == "r"
    assert extract_reasoning({"choices": [{"message": {}}]}, CHAT) == ""
    assert extract_reasoning({}, CHAT) == ""


def test_extract_reasoning_responses_returns_empty() -> None:
    assert extract_reasoning({"output": []}, RESP) == ""


# ── parse_sse_event ──


def test_parse_sse_anthropic_thinking() -> None:
    ev = {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "hmm"}}
    assert parse_sse_event(ev, ANTH) == ("", "hmm")


def test_parse_sse_anthropic_text() -> None:
    ev = {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hi"}}
    assert parse_sse_event(ev, ANTH) == ("hi", "")


def test_parse_sse_anthropic_other() -> None:
    assert parse_sse_event({"type": "message_start"}, ANTH) == ("", "")
    assert parse_sse_event({"type": "content_block_delta"}, ANTH) == ("", "")


def test_parse_sse_responses() -> None:
    assert parse_sse_event({"type": "response.output_text.delta", "delta": "tok"}, RESP) == ("tok", "")
    assert parse_sse_event({"type": "other"}, RESP) == ("", "")


def test_parse_sse_chat_token_and_reasoning() -> None:
    ev = {"choices": [{"delta": {"content": "hi", "reasoning_content": "why"}}]}
    assert parse_sse_event(ev, CHAT) == ("hi", "why")


def test_parse_sse_chat_reasoning_key() -> None:
    ev = {"choices": [{"delta": {"reasoning": "r"}}]}
    assert parse_sse_event(ev, CHAT) == ("", "r")


def test_parse_sse_chat_empty_and_bad_delta() -> None:
    assert parse_sse_event({}, CHAT) == ("", "")
    assert parse_sse_event({"choices": [{"delta": "x"}]}, CHAT) == ("", "")
    assert parse_sse_event({"choices": [{"delta": {}}]}, CHAT) == ("", "")
