"""Build LLM request bodies: construct URL and payload by protocol (openai_chat / anthropic_messages / openai_responses).

Keep each protocol's request-body shape distinct instead of unifying them; delegate protocol-specific
message/tool conversion to :mod:`anthropic_converters` / :mod:`responses_converters`.
"""

from __future__ import annotations

from typing import Any

from realmock.platform.core.constants import LLMProtocol

from .anthropic_converters import _anthropic_messages, _anthropic_tool_choice, _anthropic_tools
from .responses_converters import _responses_input, _responses_tools

# Thinking intensity → Anthropic extended thinking budget (tokens)
_ANTHROPIC_THINKING_BUDGET = {
    "low": 4096,
    "medium": 8192,
    "high": 16384,
    "max": 32768,
}


def _system_text(messages: list[dict[str, Any]], system: str | None) -> str:
    """Explicit system takes precedence, otherwise the system role content in internal messages is spliced."""
    parts = [str(m.get("content") or "") for m in messages if m.get("role") == "system"]
    return system or "\n".join(part for part in parts if part)


def build_request(
    protocol: str,
    api_base: str,
    model: str,
    max_tokens: int,
    reasoning_effort: str | None,
    messages: list[dict[str, Any]],
    system: str | None = None,
    stream: bool = False,
    temperature: float = 0.7,
    response_format: dict[str, str] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    full_url: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Construct the request URL and payload according to the protocol (the three shapes are maintained separately and are not unified with each other).

    ``full_url`` providers use ``api_base`` verbatim as the endpoint; only the URL is affected,
    the payload still follows the protocol shape.
    """
    if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
        message_items = _anthropic_messages(messages)
        system_text = _system_text(messages, system)
        url = api_base if full_url else f"{api_base}/v1/messages"
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": message_items,
            "stream": stream,
        }
        if system_text:
            payload["system"] = system_text
        anthropic_tools = _anthropic_tools(tools)
        if anthropic_tools:
            payload["tools"] = anthropic_tools
        if tool_choice is not None:
            payload["tool_choice"] = _anthropic_tool_choice(tool_choice)
        if reasoning_effort:
            # Thinking effort → extended thinking budget. Anthropic semantics: max_tokens
            # Covers both parts of thinking + answers, and must be greater than budget_tokens; the answer limit is
            # The caller retains max_tokens in full and thinks the budget is appended on top of it.
            budget = _ANTHROPIC_THINKING_BUDGET.get(reasoning_effort, 8192)
            payload["max_tokens"] = budget + max(max_tokens, 1024)
            payload["thinking"] = {"type": "enabled", "budget_tokens": budget}
        return url, payload

    if protocol == LLMProtocol.OPENAI_RESPONSES:
        message_items = _responses_input(messages)
        system_text = _system_text(messages, system)
        url = api_base if full_url else f"{api_base}/responses"
        payload = {
            "model": model,
            "input": message_items,
            "max_output_tokens": max_tokens,
            "stream": stream,
        }
        if system_text:
            payload["instructions"] = system_text
        if response_format:
            payload["text"] = {"format": response_format}
        if reasoning_effort:
            payload["reasoning"] = {"effort": "high" if reasoning_effort == "max" else reasoning_effort}
        responses_tools = _responses_tools(tools)
        if responses_tools:
            payload["tools"] = responses_tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        return url, payload

    # Default openai_chat
    url = api_base if full_url else f"{api_base}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
    }
    if response_format:
        payload["response_format"] = response_format
    if tools:
        payload["tools"] = tools
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice
    if reasoning_effort:
        payload["reasoning_effort"] = "high" if reasoning_effort == "max" else reasoning_effort
    return url, payload


__all__ = [
    "_ANTHROPIC_THINKING_BUDGET",
    "build_request",
]
