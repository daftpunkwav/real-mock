"""Ask-user normalization: clamp model-supplied shapes into dialog events."""

from __future__ import annotations

import ast
import json
import math
import re
from typing import Any

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
                except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
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
