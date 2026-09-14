"""Ask-user dialog schema: tool declaration and locale waiting copy."""

from __future__ import annotations

from typing import Any

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
                        "(aim ≤40 chars; longer labels render truncated at 80) suitable "
                        "for a clickable control; do not pass "
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
