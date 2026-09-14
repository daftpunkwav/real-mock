"""Anthropic Messages protocol conversion: internal messages → content blocks, tool schema, and tool_choice.

Pure conversion from "internal OpenAI style → Anthropic request-body fragments" only; does not
handle request URLs / response parsing (see :mod:`protocol_translate` and :mod:`response_extract`).
"""

from __future__ import annotations

import json
from typing import Any


def _anthropic_content_blocks(content: Any) -> Any:
    """Convert OpenAI-style array content to Anthropic content blocks.

    Internal messages use OpenAI-style ``image_url`` image blocks; the Anthropic Messages API
    accepts only ``text`` / ``image`` blocks. Passing them through unchanged causes the gateway to reject them
    (400 unsupported content type 'image_url'), so convert them here in one place.
    """
    if not isinstance(content, list):
        return content or ""
    blocks: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            blocks.append({"type": "text", "text": str(part)})
            continue
        ptype = part.get("type")
        if ptype == "image_url":
            url = ((part.get("image_url") or {}).get("url")) or ""
            if url.startswith("data:"):
                header, _, data = url.partition(",")
                media_type = header[5:].split(";", 1)[0] or "image/jpeg"
                blocks.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": data},
                })
            elif url:
                blocks.append({"type": "image", "source": {"type": "url", "url": url}})
            continue
        if ptype == "text":
            blocks.append({"type": "text", "text": str(part.get("text") or "")})
            continue
        blocks.append(part)
    return blocks


def _anthropic_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert internal OpenAI style messages into Anthropic content blocks."""
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
        if role == "tool":
            converted.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": message.get("tool_call_id") or "",
                            "content": str(message.get("content") or ""),
                        }
                    ],
                }
            )
            continue
        tool_calls = message.get("tool_calls") or []
        if role == "assistant" and tool_calls:
            blocks: list[dict[str, Any]] = []
            if message.get("content"):
                blocks.append({"type": "text", "text": str(message["content"])})
            for call in tool_calls:
                function = call.get("function") or {}
                arguments = function.get("arguments") or {}
                try:
                    arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
                except json.JSONDecodeError:
                    arguments = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call.get("id") or "",
                        "name": function.get("name") or "",
                        "input": arguments,
                    }
                )
            converted.append({"role": "assistant", "content": blocks})
            continue
        converted.append({
            "role": role or "user",
            "content": _anthropic_content_blocks(message.get("content")),
        })
    return converted


def _anthropic_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    converted: list[dict[str, Any]] = []
    for tool in tools:
        function = tool.get("function") if tool.get("type") == "function" else tool
        if not isinstance(function, dict):
            continue
        converted.append(
            {
                "name": function.get("name") or "",
                "description": function.get("description") or "",
                "input_schema": function.get("parameters") or {"type": "object"},
            }
        )
    return converted


def _anthropic_tool_choice(value: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, str):
        return {"type": value}
    if value.get("type") == "function":
        function = value.get("function") or {}
        return {"type": "tool", "name": function.get("name") or ""}
    return value


__all__ = [
    "_anthropic_messages",
    "_anthropic_tools",
    "_anthropic_tool_choice",
]
