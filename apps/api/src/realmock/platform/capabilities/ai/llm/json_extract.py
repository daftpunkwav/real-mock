"""Recover JSON objects from noisy LLM output.

LLM final messages are dirty: prose around the JSON, markdown fences, or
several draft objects. This module scans string-aware balanced ``{...}``
spans and keeps the key-richest candidate so callers only fall back to a
slow evidence-repair pass on genuinely unrecoverable output.

Single source for the resume-review finalizer and the records report
finalizer, which previously carried near-duplicate copies.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from realmock.platform.capabilities.ai.llm.client.json_response import auto_close_brackets
from realmock.platform.capabilities.ai.llm.client.openai_transport import (
    repair_common_json_errors,
    strip_code_fences,
)

_DEFAULT_MAX_CANDIDATES = 200


def iter_balanced_objects(
    text: str, *, max_candidates: int = _DEFAULT_MAX_CANDIDATES
) -> Iterator[str]:
    """Yield string-aware balanced ``{...}`` spans; braces inside strings are ignored.

    Stops after ``max_candidates`` spans: callers keep the key-richest
    candidate, so scanning beyond a few hundred objects only burns CPU and
    allocations. Depth is an int counter (no recursion), and a stray ``}``
    never drives it negative.
    """
    depth = 0
    start = -1
    in_string = False
    escaped = False
    yielded = 0
    for i, ch in enumerate(text):
        if yielded >= max_candidates:
            break
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            if in_string:
                escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    yield text[start : i + 1]
                    start = -1
                    yielded += 1


def extract_json_object(
    text: str | None, *, max_candidates: int = _DEFAULT_MAX_CANDIDATES
) -> dict[str, Any] | None:
    """Recover a JSON object from a noisy message; key-richest candidate wins."""
    blob = strip_code_fences((text or "").strip())
    if not blob:
        return None
    try:
        data = json.loads(blob)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    best: dict[str, Any] | None = None
    for candidate in iter_balanced_objects(blob, max_candidates=max_candidates):
        if len(candidate) < 2:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and (best is None or len(data) > len(best)):
            best = data
    return best


def _unclosed_object_starts(blob: str) -> list[int]:
    """Indices of ``{`` still unclosed at the end, outermost first (string-aware)."""
    stack: list[int] = []
    in_string = False
    escaped = False
    for i, ch in enumerate(blob):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            if in_string:
                escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            stack.append(i)
        elif ch == "}" and stack:
            stack.pop()
    # A cut inside a bare string is fine: its enclosing object start is still
    # on the stack and auto-close closes the string before the braces.
    return stack


def salvage_truncated_object(text: str | None) -> dict[str, Any] | None:
    """Recover the head of a JSON object whose tail was cut off.

    ``extract_json_object`` only parses complete balanced spans, so output
    truncated by an output-token cap (never balanced again) falls through it.
    This anchors on the unclosed ``{`` spans and closes them string-aware,
    applying the same repair ladder as :func:`parse_chat_json`. Returns None
    when nothing JSON-shaped can be recovered locally.
    """
    blob = strip_code_fences((text or "").strip())
    if not blob:
        return None
    for start in _unclosed_object_starts(blob):
        candidate = blob[start:]
        for attempt in (
            repair_common_json_errors(candidate),
            auto_close_brackets(candidate),
            repair_common_json_errors(auto_close_brackets(candidate)),
        ):
            try:
                data = json.loads(attempt)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
    return None


def truncate_chunk(text: str, *, limit: int) -> str:
    """Cap one evidence chunk; keep head+tail with an explicit marker.

    Never a silent mid-string cut: downstream repair prompts must be able to
    see that content was omitted.
    """
    if len(text) <= limit:
        return text
    keep = max(80, (limit - 80) // 2)
    return (
        text[:keep]
        + f"\n…[chunk truncated; original {len(text)} chars]…\n"
        + text[-keep:]
    )


__all__ = ["extract_json_object", "iter_balanced_objects", "salvage_truncated_object", "truncate_chunk"]
