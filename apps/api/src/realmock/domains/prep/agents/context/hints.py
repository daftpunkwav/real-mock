"""Per-turn prompt suffixes: reply-language and context-usage hints plus locale helpers."""

from __future__ import annotations

import re
from typing import Any

from realmock.domains.prep.agents.context.markers import LANG_HINT_MARKER, USAGE_HINT_MARKER
from realmock.platform.capabilities.ai.context.estimation import estimate_messages_tokens
from realmock.platform.capabilities.ai.llm.defaults import DEFAULT_CONTEXT_WINDOW

# Reply-language inference (local CJK heuristic; mirrors the resume domain's
# locale rule without a cross-domain import: CJK-heavy -> zh-CN, else en).
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_MIN_CJK_CHARS = 8
_MIN_LATIN_CHARS = 20
_UI_LOCALES = ("zh-CN", "en")


def normalize_ui_locale(raw: Any) -> str:
    """Keep only supported UI locales; anything else means unknown."""
    text = str(raw or "").strip()
    return text if text in _UI_LOCALES else ""


def infer_text_locale(*parts: Any) -> str:
    """Infer zh-CN vs en from text content (resume-derived); defaults to zh-CN."""
    text = "\n".join(str(p) for p in parts if p)
    if not text.strip():
        return "zh-CN"
    sample = text[:8_000]
    cjk = len(_CJK_RE.findall(sample))
    if cjk >= _MIN_CJK_CHARS:
        return "zh-CN"
    latin = sum(1 for ch in sample if ch.isascii() and ch.isalpha())
    if latin >= _MIN_LATIN_CHARS:
        return "en"
    return "zh-CN"


def build_lang_hint(ui_locale: str | None) -> str:
    """Per-turn reply-language suffix (stable text per locale, cache-friendly).

    The model must match the latest user message first and the UI language
    second; the ask_user dialog and waiting line follow the same language.
    """
    ui = normalize_ui_locale(ui_locale)
    return (
        f"{LANG_HINT_MARKER} The UI language is {ui or 'unknown'}. "
        "Always reply, ask, and reason in the user's message language — match the "
        "latest user message first, UI language second. The ask_user question/options "
        "and the waiting line must use that language too: never emit English UI copy "
        "when the user writes Chinese, and vice versa."
    )


def upsert_lang_hint(
    messages: list[dict[str, Any]], ui_locale: str | None
) -> list[dict[str, Any]]:
    """Refresh the trailing reply-language suffix: strip older copies, append one.

    Idempotent across turns (no accumulation in persisted history) and position
    stable (always the last message), so only the suffix itself re-caches.
    """
    out = [
        m for m in messages
        if not (
            isinstance(m, dict)
            and m.get("role") == "system"
            and isinstance(m.get("content"), str)
            and str(m.get("content")).startswith(LANG_HINT_MARKER)
        )
    ]
    out.append({"role": "system", "content": build_lang_hint(ui_locale)})
    return out


def build_usage_hint(messages: list[dict[str, Any]], context_window: int) -> str:
    """Per-turn context-usage suffix (one volatile line at the very tail).

    Lives in a trailing system message instead of the compact tool description:
    the tools array sits at the head of the provider request, so a per-turn
    description there would invalidate the whole prompt-cache prefix every turn.
    """
    window = context_window if context_window and context_window > 0 else DEFAULT_CONTEXT_WINDOW
    usage = estimate_messages_tokens(messages or [])
    share = round(usage * 100 / window) if window > 0 else 0
    return (
        f"{USAGE_HINT_MARKER} The conversation context is about {usage} of {window} "
        f"tokens (~{share}% used). Weigh this when deciding whether compact_context "
        "is worth a call this turn."
    )


def upsert_usage_hint(
    messages: list[dict[str, Any]], context_window: int
) -> list[dict[str, Any]]:
    """Refresh the trailing context-usage suffix: strip older copies, append one.

    Idempotent across turns (no accumulation in persisted history) and always
    last, so only the suffix itself re-caches.
    """
    out = [
        m for m in messages
        if not (
            isinstance(m, dict)
            and m.get("role") == "system"
            and isinstance(m.get("content"), str)
            and str(m.get("content")).startswith(USAGE_HINT_MARKER)
        )
    ]
    out.append({"role": "system", "content": build_usage_hint(out, context_window)})
    return out


__all__ = [
    "build_lang_hint",
    "build_usage_hint",
    "infer_text_locale",
    "normalize_ui_locale",
    "upsert_lang_hint",
    "upsert_usage_hint",
]
