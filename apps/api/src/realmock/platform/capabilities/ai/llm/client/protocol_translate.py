"""Build LLM request bodies: construct URL and payload by protocol (openai_chat / anthropic_messages / openai_responses).

Keep each protocol's request-body shape distinct instead of unifying them; delegate protocol-specific
message/tool conversion to :mod:`anthropic_converters` / :mod:`responses_converters`.

Reasoning effort: the default scale is low/medium/high/max. A model may declare its own ordered
level list (``reasoning_variants``); any level outside the default scale is then passed through
verbatim — providers ignore or reject what they do not know, and the user picked it deliberately.
"""

from __future__ import annotations

from typing import Any

from realmock.platform.core.constants import LLMProtocol

from .anthropic_converters import _anthropic_messages, _anthropic_tool_choice, _anthropic_tools
from .responses_converters import _responses_input, _responses_tool_choice, _responses_tools

# Default thinking scale → Anthropic extended thinking budget (tokens).
_ANTHROPIC_THINKING_BUDGET = {
    "low": 4096,
    "medium": 8192,
    "high": 16384,
    "max": 32768,
}

# Labels with dedicated Anthropic thinking shapes (compat endpoints).
_ANTHROPIC_THINKING_MODES = {"adaptive": "adaptive", "off": "disabled", "none": "disabled", "disabled": "disabled"}

# OpenAI's reasoning_effort/effort fields have no "max" level.
_OPENAI_EFFORT_ALIASES = {"max": "high"}


def _anthropic_thinking_param(effort: str, variants: list[str] | None) -> dict[str, Any]:
    """Map an effort label to the Anthropic ``thinking`` parameter.

    Known labels use the budget table; ``adaptive``/off-style labels pass as
    modes; any other custom label interpolates a budget from its position in
    the model's declared variant list (4k → 32k).
    """
    mode = _ANTHROPIC_THINKING_MODES.get(effort.lower())
    if mode is not None:
        return {"type": mode}
    budget = _ANTHROPIC_THINKING_BUDGET.get(effort)
    if budget is None:
        budget = _interpolated_budget(effort, variants)
    return {"type": "enabled", "budget_tokens": budget}


def _interpolated_budget(effort: str, variants: list[str] | None) -> int:
    """Budget for a custom label: position-based between low (4k) and max (32k)."""
    if variants and effort in variants:
        index = variants.index(effort)
        last = max(len(variants) - 1, 1)
        return 4096 + int((32768 - 4096) * index / last)
    return 8192


def _openai_effort(effort: str) -> str:
    """Effort label for OpenAI-shaped fields: alias "max"→"high", pass
    everything else (including custom declared variants) through verbatim."""
    return _OPENAI_EFFORT_ALIASES.get(effort, effort)


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
    reasoning_variants: list[str] | None = None,
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
            # Thinking effort → the ``thinking`` parameter. Anthropic semantics:
            # when thinking is enabled, max_tokens must cover thinking + answer
            # and exceed budget_tokens, so the budget is appended on top of the
            # caller's max_tokens (floored at 1024 for the answer part). Mode
            # shapes (adaptive/disabled) carry no budget, so max_tokens is sent
            # as-is. Temperature is only sent without thinking: the official
            # API rejects the combination when thinking is on.
            thinking = _anthropic_thinking_param(reasoning_effort, reasoning_variants)
            payload["max_tokens"] = max_tokens
            if thinking.get("type") == "enabled":
                payload["max_tokens"] = thinking["budget_tokens"] + max(max_tokens, 1024)
            payload["thinking"] = thinking
        elif temperature is not None:
            payload["temperature"] = temperature
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
            payload["reasoning"] = {"effort": _openai_effort(reasoning_effort)}
        responses_tools = _responses_tools(tools)
        if responses_tools:
            payload["tools"] = responses_tools
        if tool_choice is not None:
            payload["tool_choice"] = _responses_tool_choice(tool_choice)
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
        payload["reasoning_effort"] = _openai_effort(reasoning_effort)
    return url, payload


__all__ = [
    "_ANTHROPIC_THINKING_BUDGET",
    "build_request",
]
