"""Prep ask_user control-flow tool: schema, dialog-shape normalization, inline XML recovery, and dialog dispatch.

``ask_user`` requires intervention from the agent layer (dialog + loop termination), so it does
not enter the domain-tool registry (:mod:`tools`) and lives in this module separately; the
    orchestration layer calls only :func:`dispatch_ask_user` and :func:`extract_inline_ask_user`.

Dialog shapes: one dialog carries 1–8 questions — the ``questions`` array of per-question
``{question, options, selection, widget, scale, allow_custom, suggested_index}`` objects, or the
flat single-question shorthand. ``selection`` (single radio / multi checkbox) and ``widget``
(options list, numeric slider, star rating) are decided by the model and clamped by the
``normalize_ask_*`` helpers; a free-text input is always offered unless ``allow_custom`` is false.
Emitted events keep the flat first-question fields and add a ``questions`` list only when
several questions survived, so the single-question consumer contract is unchanged.
"""

from __future__ import annotations

import ast
import asyncio
import json
import math
import re
from typing import Any

from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.ai.agent.loop import AgentHalt

# Control-flow tool: requires agent-layer intervention (dialog + loop halt), so it
# does not enter the domain-tool registry. ASK_USER_TOOL is the public schema;
# _ASK_USER_TOOL remains as a backward-compatible alias.
ASK_USER_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "ask_user",
        "description": (
            "Show an interactive dialog: call only when the user must answer focused "
            "question(s) (e.g. target role/company/direction undecided, A vs B next step). "
            "Ask 1–8 questions in ONE dialog via the questions array — batch several only "
            "when the decision genuinely needs multiple inputs, and prefer one question "
            "when that suffices. At most one dialog per reply. You decide the shape per "
            "question: selection=single (radio list) or multi (checkbox list, answers are "
            "joined); widget=options, slider, or rating. A free-text input is always shown "
            "(allow_custom), so never add an 'other' option. The flat top-level fields are "
            "a single-question shorthand equivalent to a one-item questions array."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "maxItems": 8,
                    "minItems": 1,
                    "description": (
                        "1–8 question objects, each {question, options, selection, widget, "
                        "scale, allow_custom, suggested_index} with the same rules as the "
                        "flat single-question fields. Takes precedence over the flat form "
                        "when both are given."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string", "description": "One sentence"},
                            "options": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "2–8 short plain-text labels (widget=options only)",
                            },
                            "selection": {
                                "type": "string",
                                "enum": ["single", "multi"],
                            },
                            "widget": {
                                "type": "string",
                                "enum": ["options", "slider", "rating"],
                            },
                            "scale": {"type": "object"},
                            "allow_custom": {"type": "boolean"},
                            "suggested_index": {"type": "integer"},
                        },
                        "required": ["question"],
                    },
                },
                "question": {
                    "type": "string",
                    "description": "Single-question shorthand: the question to ask (one sentence)",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "2–8 options for widget=options. Each must be a short plain-text label "
                        "(≤40 chars) suitable for a clickable control; do not pass "
                        "{description: ..., value: ...} objects or pseudo-JSON strings. "
                        "Ignored for slider/rating widgets."
                    ),
                },
                "selection": {
                    "type": "string",
                    "enum": ["single", "multi"],
                    "description": (
                        "single (default): pick exactly one, rendered as radio circles. "
                        "multi: pick any number, rendered as checkboxes."
                    ),
                },
                "widget": {
                    "type": "string",
                    "enum": ["options", "slider", "rating"],
                    "description": (
                        "options (default): clickable option list. slider: numeric range, "
                        "requires scale {min, max} plus optional step/unit. rating: star "
                        "rating, optional scale {max} (3–10, default 5)."
                    ),
                },
                "scale": {
                    "type": "object",
                    "description": (
                        "Widget parameters. slider: {min: number, max: number (min < max), "
                        "step: positive number (default 1), unit: short suffix string}. "
                        "rating: {max: star count 3–10 (default 5)}."
                    ),
                },
                "allow_custom": {
                    "type": "boolean",
                    "description": "Show the always-on free-text input (default true).",
                },
                "suggested_index": {
                    "type": "integer",
                    "description": (
                        "Index into options marking YOUR recommended choice (default 0). "
                        "The UI auto-submits it if the user does not answer in time. "
                        "Only meaningful for widget=options."
                    ),
                },
            },
            # Either the questions array or the flat shorthand validates; the
            # normalization layer rejects shapes that render no dialog.
        },
    },
}

_ASK_USER_TOOL = ASK_USER_TOOL

ASK_USER_FALLBACK_REPLY = (
    "I'm waiting for your answer — respond in the dialog, or type it directly."
)

# Backward-compatible alias.
_ASK_USER_FALLBACK_REPLY = ASK_USER_FALLBACK_REPLY

# Waiting-line copy per reply locale (streamed visibly when the dialog opens).
_ASK_USER_FALLBACK_REPLIES = {
    "zh-CN": "我在等你作答 — 请在弹窗中选择，或直接输入。",
    "en": ASK_USER_FALLBACK_REPLY,
}


def fallback_reply(locale: str | None) -> str:
    """Visible waiting line in the user's language (defaults to English)."""
    return _ASK_USER_FALLBACK_REPLIES.get(locale or "", ASK_USER_FALLBACK_REPLY)

# Option-count bounds (the persistent free-text input is separate, not counted).
_ASK_MIN_OPTIONS = 2
_ASK_MAX_OPTIONS = 8
_ASK_OPT_MAX_CHARS = 80

_ASK_SELECTIONS = ("single", "multi")
_ASK_WIDGETS = ("options", "slider", "rating")
_ASK_DEFAULT_RATING_MAX = 5
_ASK_RATING_MIN_STARS = 3
_ASK_RATING_MAX_STARS = 10
_ASK_ALLOW_CUSTOM_FALSE_STRINGS = frozenset({"false", "no", "off", "0"})

# Tolerantly parse description/value in pseudo-JSON options (key is recognized with or without quotes)
_ASK_OPT_DESC_RE = re.compile(r"description['\"]?\s*[:=]\s*['\"](.+?)['\"]", re.S)
_ASK_OPT_VALUE_RE = re.compile(r"value['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]")

_ASK_OPT_DICT_KEYS = ("description", "value", "label", "text")


def _normalize_ask_option(raw: Any) -> str:
    """Normalize a single option supplied by the LLM into plain text ready for display/transmission.

    The model occasionally violates the schema and writes an option as a ``{"description": ..., "value": ...}``
    dict or pseudo-JSON string; extract the human-readable description consistently and fall back to the original value.
    """
    obj: Any = raw
    if isinstance(raw, str):
        text = raw.strip()
        if text[:1] in "{[":
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                try:
                    obj = ast.literal_eval(text)
                except (ValueError, SyntaxError, MemoryError, RecursionError):
                    obj = text
    if isinstance(obj, dict):
        for key in _ASK_OPT_DICT_KEYS:
            value = str(obj.get(key, "") or "").strip()
            if value:
                return value
        return ""
    if isinstance(obj, str):
        text = obj.strip()
        match = _ASK_OPT_DESC_RE.search(text) or _ASK_OPT_VALUE_RE.search(text)
        if match:
            return match.group(1).strip()
        return text
    return str(obj).strip()


def normalize_ask_options(raw_options: Any) -> list[str]:
    """Normalize the option list into plain-text labels (each ≤80 chars, at most 8 kept).

    Duplicates are dropped (order kept): repeated labels would collide as
    dialog keys and toggle ambiguously in multi-select.
    """
    seen: set[str] = set()
    cleaned: list[str] = []
    for opt in (_normalize_ask_option(o) for o in (raw_options or [])):
        if opt and opt not in seen:
            seen.add(opt)
            cleaned.append(opt[:_ASK_OPT_MAX_CHARS])
    return cleaned[:_ASK_MAX_OPTIONS]


def normalize_ask_selection(raw: Any) -> str:
    """Clamp the selection mode; anything unknown falls back to single."""
    mode = str(raw or "").strip().lower()
    return mode if mode in _ASK_SELECTIONS else "single"


def normalize_ask_widget(raw: Any) -> str:
    """Clamp the widget type; anything unknown falls back to options."""
    widget = str(raw or "").strip().lower()
    return widget if widget in _ASK_WIDGETS else "options"


def normalize_ask_allow_custom(raw: Any) -> bool:
    """Whether the free-text input stays on; only explicit negatives turn it off."""
    if isinstance(raw, str):
        return raw.strip().lower() not in _ASK_ALLOW_CUSTOM_FALSE_STRINGS
    return False if raw is False or raw == 0 else True


def _as_number(value: Any) -> float | None:
    """Coerce a scale bound to a finite float; booleans and non-numeric input yield None."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_ask_scale(widget: str, raw: Any) -> dict[str, Any] | None:
    """Validate widget parameters. Returns the cleaned scale dict, or None when unusable.

    slider needs numeric min < max (step defaults to 1, unit to ""); rating takes
    an optional star count clamped to 3–10 (default 5). options ignores scale.
    """
    if widget == "options":
        return {}
    data = raw if isinstance(raw, dict) else None
    if widget == "rating":
        maximum = _as_number((data or {}).get("max"))
        if maximum is None:
            return {"max": _ASK_DEFAULT_RATING_MAX}
        return {"max": int(min(_ASK_RATING_MAX_STARS, max(_ASK_RATING_MIN_STARS, round(maximum))))}
    if widget == "slider":
        if data is None:
            return None
        minimum, maximum = _as_number(data.get("min")), _as_number(data.get("max"))
        if minimum is None or maximum is None or not minimum < maximum:
            return None
        step = _as_number(data.get("step"))
        if step is None or step <= 0:
            step = 1.0
        unit = str(data.get("unit") or "").strip()[:12]
        return {"min": minimum, "max": maximum, "step": step, "unit": unit}
    return None


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


def _build_ask_event(
    question: str,
    options: list[str],
    *,
    selection: Any = "single",
    widget: Any = "options",
    scale: Any = None,
    allow_custom: Any = True,
    suggested_index: Any = 0,
) -> dict[str, Any] | None:
    """Assemble a dialog event, or None when the arguments cannot render a dialog.

    options widgets need ≥2 options; slider/rating widgets need a valid scale
    (with options optional). An invalid slider/rating scale degrades to the
    options widget when options are sufficient, so the question survives.
    ``suggested`` is the auto-submit answer on UI timeout (options only).
    """
    question = str(question or "").strip()
    widget = normalize_ask_widget(widget)
    cleaned_scale = normalize_ask_scale(widget, scale)
    if cleaned_scale is None:
        if widget != "options" and len(options) >= _ASK_MIN_OPTIONS:
            widget, cleaned_scale = "options", {}
        else:
            return None
    if widget == "options" and len(options) < _ASK_MIN_OPTIONS:
        return None
    if not question:
        return None
    return {
        "question": question[:200],
        "options": options,
        "selection": normalize_ask_selection(selection),
        "widget": widget,
        "scale": cleaned_scale,
        "allow_custom": normalize_ask_allow_custom(allow_custom),
        "suggested": _resolve_suggested(widget, options, cleaned_scale, suggested_index),
    }


def _resolve_suggested(
    widget: str, options: list[str], scale: dict[str, Any], suggested_index: Any
) -> str | None:
    """Resolve the recommended auto-submit answer (options/slider only)."""
    if widget == "rating":
        return None
    if widget == "slider":
        return f"{scale.get('min')}{scale.get('unit') or ''}"
    try:
        index = int(suggested_index)
    except (TypeError, ValueError):
        index = 0
    index = max(0, min(len(options) - 1, index))
    return options[index]


# One dialog may carry up to this many questions.
_ASK_MAX_QUESTIONS = 8

# Per-question raw keys lifted from a questions-array item (same names as the
# flat single-question shorthand, so one builder serves both shapes).
_ASK_ITEM_FIELDS = (
    "question", "options", "selection", "widget", "scale", "allow_custom", "suggested_index",
)


def normalize_ask_questions(args: Any) -> list[dict[str, Any]] | None:
    """Build 1–8 validated dialog events from the raw tool arguments.

    A non-empty ``questions`` array wins; otherwise the flat single-question
    fields are treated as a one-item list (an empty array falls back to the
    flat form too). Invalid items are skipped; ``None`` when no question
    survives (the caller answers with the args-incomplete text).
    """
    data = args if isinstance(args, dict) else {}
    raw_items = data.get("questions")
    specs: list[dict[str, Any]] = []
    if isinstance(raw_items, list) and raw_items:
        for item in raw_items:
            if isinstance(item, dict):
                specs.append({key: item.get(key) for key in _ASK_ITEM_FIELDS})
    elif data.get("question"):
        specs.append({key: data.get(key) for key in _ASK_ITEM_FIELDS})
    events: list[dict[str, Any]] = []
    for spec in specs:
        event = _build_ask_event(
            spec.get("question"),
            normalize_ask_options(spec.get("options")),
            selection=spec.get("selection"),
            widget=spec.get("widget"),
            scale=spec.get("scale"),
            allow_custom=spec.get("allow_custom", True),
            suggested_index=spec.get("suggested_index", 0),
        )
        if event is not None:
            events.append(event)
    # The 1–8 bound applies to VALID questions: an invalid item never burns a slot.
    return events[:_ASK_MAX_QUESTIONS] or None


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


async def dispatch_ask_user(
    *,
    args: Any,
    memory: WorkingMemory,
    events: asyncio.Queue | None = None,
    search_groups: list[dict[str, Any]] | None = None,
    asked_user: dict[str, bool] | None = None,
) -> str:
    """Execute the ask_user tool: validate, write memory, emit a dialog event, and terminate the loop.

    Accepts the raw tool arguments (``questions`` array of 1–8 items, or the flat
    single-question shorthand). When no question survives validation, return
    explanatory text (as the tool observation, prompting the model to ask in the
    response body instead); otherwise, write to working memory, emit the
    ``ask_user`` event, and raise :class:`AgentHalt`. The event carries the flat
    fields of the FIRST question plus a ``questions`` list only when several
    survived, so the single-question contract stays unchanged.
    """
    dialog_events = normalize_ask_questions(args)
    if not dialog_events:
        return (
            "ask_user args incomplete: provide 1–8 question objects via `questions` "
            "(or the flat `question` shorthand), each with a question plus 2–8 options "
            "(options widget) or a valid scale {min, max} / {max stars} "
            "(slider/rating widget). "
            "Ask the user directly in your reply instead."
        )
    questions_line = " | ".join(str(e["question"]) for e in dialog_events)
    memory.remember("note", f"Asked user: {questions_line}")
    if asked_user is not None:
        asked_user["on"] = True
    if events is not None:
        # First reissue the previously generated search cards to ensure that the order of card events before the pop-up window is correct.
        if search_groups:
            await events.put({
                "type": "search_results",
                "groups": list(search_groups),
            })
        event: dict[str, Any] = dict(dialog_events[0])
        if len(dialog_events) > 1:
            event["questions"] = dialog_events
        await events.put({"type": "ask_user", **event})
    raise AgentHalt(
        "Dialog shown to the user; waiting for their answer. "
        "This turn ends here: do not call more tools; wait for the next user input."
    )


__all__ = [
    "ASK_USER_TOOL",
    "ASK_USER_FALLBACK_REPLY",
    "_ASK_USER_TOOL",
    "_ASK_USER_FALLBACK_REPLY",
    "dispatch_ask_user",
    "normalize_ask_questions",
    "extract_inline_ask_user",
    "_extract_inline_ask_user",
    "fallback_reply",
    "normalize_ask_allow_custom",
    "normalize_ask_options",
    "normalize_ask_scale",
    "normalize_ask_selection",
    "normalize_ask_widget",
]
