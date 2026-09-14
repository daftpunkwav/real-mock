"""Inline ask-user recovery: rescue body-text tool-call drift into dialog events."""

from __future__ import annotations

import json
import re
from typing import Any

from realmock.domains.prep.agents.ask_user.normalize import (
    _ASK_MAX_QUESTIONS,
    _build_ask_event,
    normalize_ask_options,
)


# Inline tool-call blocks in the body (function calling protocol drift: <tool_call>…</tool_call>)
_INLINE_TOOL_BLOCK_RE = re.compile(r"<tool_call>.*?</tool_call>", re.S)
# Two common ask_user forms inside a block: JSON arguments and <parameter> tags
_INLINE_PARAM_RE = re.compile(
    r"<parameter\s+name=[\"'](?P<key>question|options|selection|widget)[\"']\s*>(?P<value>.*?)</parameter>",
    re.S,
)


def _parse_inline_ask_args(raw: str) -> dict[str, Any] | None:
    """Try to parse ask_user's question/options/selection/widget from the inline block text."""
    candidate = raw.strip()
    # Form 1: JSON (arguments may be nested objects or strings)
    start, end = candidate.find("{"), candidate.rfind("}")
    if 0 <= start < end:
        try:
            data = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            args = data.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = None
            if isinstance(args, dict) and args.get("question"):
                return args
    # Form 2: <parameter name="question">…</parameter> tag
    params: dict[str, Any] = {}
    for m in _INLINE_PARAM_RE.finditer(candidate):
        key, value = m.group("key"), m.group("value").strip()
        if key == "options":
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    params["options"] = parsed
                    continue
            except json.JSONDecodeError:
                pass
            params["options"] = [line.strip(" -") for line in value.splitlines() if line.strip(" -")]
        else:
            params[key] = value
    if params.get("question"):
        return params
    return None



def extract_inline_ask_user(text: str) -> tuple[str, dict[str, Any] | None]:
    """Recover inlined ask_user tool calls from the final body text.

    The model occasionally degrades ask_user to body-text XML ( ``<tool_call><invoke name="ask_user">…`` )
    instead of using the tool channel; silently cleaning these blocks would leave the user seeing "about to ask a question" before the response stops.
    Up to 8 ask_user blocks are collected into ONE dialog event (multiple questions);
    the blocks themselves are always removed from the body, and all other inline blocks
    are preserved for centralized cleanup by :func:`sanitize_special_tokens`.
    Return ``(cleaned body, ask event or None)``.
    """
    collected: list[dict[str, Any]] = []
    changed = False

    def _sub(m: re.Match[str]) -> str:
        nonlocal changed
        block = m.group(0)
        if "ask_user" in block:
            changed = True
            if len(collected) < _ASK_MAX_QUESTIONS:
                args = _parse_inline_ask_args(block)
                if args:
                    collected.append(args)
            # ask_user drift is always stripped so raw XML never reaches the
            # user; the remaining prose flows through the empty-body fallbacks.
            # (The invoke-style cleaner only strips blocks with <invoke>, so
            # JSON-shaped drift blocks must be removed here.)
            return ""
        return block

    cleaned = _INLINE_TOOL_BLOCK_RE.sub(_sub, text)
    if not changed:
        return text, None
    events: list[dict[str, Any]] = []
    for args in collected:
        event = _build_ask_event(
            args.get("question"),
            normalize_ask_options(args.get("options")),
            selection=args.get("selection"),
            widget=args.get("widget"),
            scale=args.get("scale"),
            allow_custom=args.get("allow_custom", True),
            suggested_index=args.get("suggested_index", 0),
        )
        if event is not None:
            events.append(event)
    if not events:
        return cleaned, None
    merged = dict(events[0])
    if len(events) > 1:
        merged["questions"] = events
    return cleaned, merged


# Backward-compatible alias.
_extract_inline_ask_user = extract_inline_ask_user
