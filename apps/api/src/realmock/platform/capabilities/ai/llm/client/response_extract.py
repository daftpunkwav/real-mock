"""LLM response parsing: extract body / tool calls / reasoning, plus incremental parsing of SSE events.

Pure-function input (response JSON or a single SSE event) + protocol, producing a unified shape;
does not make network requests (see :mod:`streaming`).
"""

from __future__ import annotations

from typing import Any

from realmock.platform.core.constants import LLMProtocol

from .protocol_utils import _json_arguments


def extract_text(data: dict[str, Any], protocol: str) -> str:
    if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
        content = data.get("content", [])
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
        return ""
    if protocol == LLMProtocol.OPENAI_RESPONSES:
        if isinstance(data.get("output_text"), str):
            return data["output_text"]
        for item in data.get("output", []) or []:
            if isinstance(item, dict) and item.get("type") == "message":
                content = item.get("content", [])
                if isinstance(content, list):
                    return "".join(c.get("text", "") for c in content if isinstance(c, dict))
                return str(content or "")
        return ""

    msg = data.get("choices", [{}])[0].get("message", {}) if data.get("choices") else {}
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    for key in ("output_text", "reasoning_content", "reasoning"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return ""


def extract_tool_calls(data: dict[str, Any], protocol: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
        for item in data.get("content", []) or []:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            calls.append(
                {
                    "id": item.get("id") or "",
                    "type": "function",
                    "function": {
                        "name": item.get("name") or "",
                        "arguments": _json_arguments(item.get("input")),
                    },
                }
            )
        return calls
    if protocol == LLMProtocol.OPENAI_RESPONSES:
        for item in data.get("output", []) or []:
            if not isinstance(item, dict) or item.get("type") != "function_call":
                continue
            calls.append(
                {
                    "id": item.get("call_id") or item.get("id") or "",
                    "type": "function",
                    "function": {
                        "name": item.get("name") or "",
                        "arguments": _json_arguments(item.get("arguments")),
                    },
                }
            )
        return calls
    choices = data.get("choices") or []
    if choices:
        return choices[0].get("message", {}).get("tool_calls") or []
    return calls


def extract_reasoning(data: dict[str, Any], protocol: str) -> str:
    """Extract reasoning text (or an empty string if absent).

    - anthropic_messages: concatenate ``thinking`` blocks in content;
    - openai_chat: use the message's ``reasoning_content`` / ``reasoning``;
    - openai_responses: reasoning items contain summaries only and most gateways do not return them, so do not extract.
    """
    if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
        content = data.get("content", [])
        if isinstance(content, list):
            return "".join(
                str(item.get("thinking") or "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "thinking"
            )
        return ""
    msg = (data.get("choices") or [{}])[0].get("message", {}) if data.get("choices") else {}
    for key in ("reasoning_content", "reasoning"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return ""


def parse_sse_event(event: dict[str, Any], protocol: str) -> tuple[str, str]:
    """Extracted from a single SSE event (body delta, think delta); unrecognized events returned ("", "")."""
    if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
        if event.get("type") == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "thinking_delta":
                return "", str(delta.get("thinking") or "")
            return str(delta.get("text") or ""), ""
        return "", ""
    if protocol == LLMProtocol.OPENAI_RESPONSES:
        if event.get("type") == "response.output_text.delta":
            return str(event.get("delta") or ""), ""
        return "", ""
    # openai_chat
    choices = event.get("choices") or []
    if not choices:
        return "", ""
    delta = choices[0].get("delta") or {}
    if not isinstance(delta, dict):
        return "", ""
    token = str(delta.get("content") or "")
    reasoning = str(delta.get("reasoning_content") or delta.get("reasoning") or "")
    return token, reasoning


__all__ = [
    "extract_text",
    "extract_tool_calls",
    "extract_reasoning",
    "parse_sse_event",
]
