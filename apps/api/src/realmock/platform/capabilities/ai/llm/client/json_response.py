"""LLM JSON output parsing: stripping think fences, code fences, and tolerant retries.

The parsing core for ``chat_json``; failures remain visible to callers (report, etc.)—this module
does not swallow errors or return fake JSON.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


async def parse_chat_json(
    chat_fn: Callable[..., Awaitable[str]],
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int | None,
) -> dict[str, Any]:
    """Request a JSON-formatted response and parse it.

    ``chat_fn`` is the bound client ``chat`` method (this module specifies response_format);
    ``max_tokens`` must accommodate the output size (for example, complete JSON from an in-depth
    résumé evaluation can exceed a small max-output budget, and truncation causes JSON parsing to fail).
    """
    content = await chat_fn(
        messages,
        temperature=temperature,
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
    )
    if not (isinstance(content, str) and content.strip()):
        logger.warning("chat_json returns empty for the first time, and returns no response_format to try again.")
        retry_messages = list(messages)
        retry_messages.append({
            "role": "user",
            "content": "Please only output a legal JSON object, no Markdown, no interpretation.",
        })
        content = await chat_fn(retry_messages, temperature=temperature)
    if content is None or (isinstance(content, str) and not content.strip()):
        raise ValueError(
            "LLM returns empty content and cannot parse JSON."
            "Please confirm that the model supports Chat Completions text output (it may currently be a reasoning-only model or one that returns empty content)."
        )
    text = content if isinstance(content, str) else str(content)
    text = text.strip()
    for open_t, close_t in (
        ("<think>", "</think>"),
        ("<thinking>", "</thinking>"),
    ):
        while True:
            lo = text.lower().find(open_t)
            if lo < 0:
                break
            hi = text.lower().find(close_t, lo + len(open_t))
            if hi < 0:
                text = text[:lo] + text[lo + len(open_t) :]
                break
            text = text[:lo] + text[hi + len(close_t) :]
    from .openai_transport import strip_code_fences

    text = strip_code_fences(text)
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # LLM long JSON three types of high-frequency impairments: trailing commas (,} /,]), naked control characters in strings,
        # The closing bracket is missing at the end (truncation/the model is closed early); fix it step by step and try again
        from .openai_transport import repair_common_json_errors

        try:
            data = json.loads(repair_common_json_errors(text))
        except json.JSONDecodeError:
            repaired = repair_common_json_errors(auto_close_brackets(text))
            if repaired != text:
                # Completion means that the output is likely to be truncated: part of the results are dropped into the database and need to be traced for investigation.
                logger.warning("LLM JSON is missing the closing character and has been automatically completed (suspected to truncate the output)")
            data = json.loads(repaired)
    if not isinstance(data, dict):
        raise ValueError("LLM JSON root type must be object")
    return data


def auto_close_brackets(text: str) -> str:
    """Complete missing closing brackets/quotes with string awareness (last-resort recovery for truncated JSON).

    Append characters only when a structure is actually unclosed; return valid JSON unchanged.
    """
    stack: list[str] = []
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
    if not in_string and not stack:
        return text
    closers = ["]" if c == "[" else "}" for c in reversed(stack)]
    if in_string:
        closers.insert(0, '"')
    return text + "".join(closers)


__all__ = ["auto_close_brackets", "parse_chat_json"]
