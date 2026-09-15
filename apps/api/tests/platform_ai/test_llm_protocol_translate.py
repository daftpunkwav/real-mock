"""Protocol translation tests for apps/api/src/realmock/platform/capabilities/ai/llm/client/protocol_translate.py.

Covers: build_request for ANTHROPIC_MESSAGES/OPENAI_RESPONSES/OPENAI_CHAT
(URLs, system extraction, tools, reasoning effort, stream flags) and _system_text fallback.

Conventions: pure functions, no network; asyncio_mode=auto.
"""

from __future__ import annotations

from realmock.platform.capabilities.ai.llm.client import protocol_translate as pt
from realmock.platform.core.constants import LLMProtocol



def test_build_request_anthropic_full() -> None:
    url, payload = pt.build_request(
        LLMProtocol.ANTHROPIC_MESSAGES,
        "https://x",
        "m",
        100,
        "medium",
        [{"role": "system", "content": "S"}, {"role": "user", "content": "hi"}],
        stream=True,
        tools=[{"type": "function", "function": {"name": "t"}}],
        tool_choice="auto",
    )
    assert url == "https://x/v1/messages"
    assert payload["system"] == "S"
    assert payload["messages"] == [{"role": "user", "content": "hi"}]
    assert payload["tools"][0]["name"] == "t"
    assert payload["tool_choice"] == {"type": "auto"}
    assert payload["thinking"] == {"type": "enabled", "budget_tokens": 8192}
    assert payload["max_tokens"] == 8192 + 1024  # max_tokens floored at 1024


def test_build_request_anthropic_system_from_messages_and_unknown_effort() -> None:
    url, payload = pt.build_request(
        LLMProtocol.ANTHROPIC_MESSAGES,
        "https://x",
        "m",
        5000,
        "ultra",
        [{"role": "system", "content": "A"}, {"role": "system", "content": ""}],
        system="explicit",
    )
    assert url.endswith("/v1/messages")
    assert payload["system"] == "explicit"
    assert payload["thinking"]["budget_tokens"] == 8192  # unknown effort → default
    assert "tools" not in payload


def test_build_request_responses_full() -> None:
    url, payload = pt.build_request(
        LLMProtocol.OPENAI_RESPONSES,
        "https://x",
        "m",
        256,
        "max",
        [{"role": "system", "content": "S"}, {"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
        tools=[{"type": "function", "function": {"name": "t"}}],
        tool_choice="auto",
    )
    assert url == "https://x/responses"
    assert payload["instructions"] == "S"
    assert payload["max_output_tokens"] == 256
    assert payload["text"] == {"format": {"type": "json_object"}}
    assert payload["reasoning"] == {"effort": "high"}
    assert payload["tools"][0]["name"] == "t"
    assert payload["tool_choice"] == "auto"


def test_build_request_responses_minimal() -> None:
    url, payload = pt.build_request(
        LLMProtocol.OPENAI_RESPONSES, "https://x", "m", 64, "low",
        [{"role": "user", "content": "hi"}],
    )
    assert url.endswith("/responses")
    assert "instructions" not in payload
    assert payload["reasoning"] == {"effort": "low"}
    assert "tools" not in payload


def test_build_request_openai_chat_full() -> None:
    msgs = [{"role": "user", "content": "hi"}]
    url, payload = pt.build_request(
        "openai_chat", "https://x", "m", 64, "max", msgs,
        temperature=0.1,
        response_format={"type": "json_object"},
        tools=[{"type": "function", "function": {"name": "t"}}],
        tool_choice="auto",
        stream=True,
    )
    assert url == "https://x/chat/completions"
    assert payload["messages"] is msgs
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["tools"][0]["function"]["name"] == "t"
    assert payload["tool_choice"] == "auto"
    assert payload["reasoning_effort"] == "high"
    assert payload["temperature"] == 0.1
    assert payload["stream"] is True


def test_build_request_openai_chat_minimal_and_plain_effort() -> None:
    url, payload = pt.build_request("nope", "https://x", "m", 64, "low", [])
    assert url.endswith("/chat/completions")
    assert payload["reasoning_effort"] == "low"
    assert "response_format" not in payload


def test_system_text_explicit_empty_falls_back() -> None:
    assert pt._system_text([{"role": "system", "content": "A"}], "") == "A"
    assert pt._system_text([{"role": "user", "content": "x"}], None) == ""
