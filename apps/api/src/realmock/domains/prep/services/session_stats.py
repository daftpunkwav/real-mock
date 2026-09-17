"""Prep session list metrics: cached summary snippet and countable message total.

Single source of truth for the coaching-session list columns (``PrepSession.summary``
/ ``PrepSession.message_count``). Writers (``PrepAgent._save``, fork/truncate paths)
compute through :func:`compute_session_summary_and_count`; the list route reads the
cached columns and falls back to the same helper for legacy rows. The helper is a
pure function over message dicts: no DB, no LLM, no imports from routes or agents,
so the dependency direction stays agents/routes -> services leaf (acyclic).
"""

from __future__ import annotations

from typing import Any

# Visible snippet length for the session list (matches the historical list
# behavior; the DB column is wider for headroom).
SESSION_SUMMARY_SNIPPET_MAX_CHARS = 48


def _is_user_text(m: Any) -> bool:
    return isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str)


def _is_countable(m: Any) -> bool:
    return (
        isinstance(m, dict)
        and m.get("role") in ("user", "assistant")
        and isinstance(m.get("content"), str)
    )


def compute_session_summary_and_count(messages: list[Any]) -> tuple[str, int]:
    """Derive the list-view summary snippet and countable message total.

    Args:
        messages: Persisted history (tolerates corrupt shapes: non-list
            input yields empty results instead of raising).

    Returns:
        ``(summary, count)`` where summary is the first user text stripped
        and capped at 48 chars, and count covers user/assistant string-content
        messages only (system/tool traffic excluded, same as the list view).
    """
    if not isinstance(messages, list):
        return "", 0
    summary = next(
        (str(m.get("content") or "").strip() for m in messages if _is_user_text(m)),
        "",
    )
    count = sum(1 for m in messages if _is_countable(m))
    return summary[:SESSION_SUMMARY_SNIPPET_MAX_CHARS], count


__all__ = [
    "SESSION_SUMMARY_SNIPPET_MAX_CHARS",
    "compute_session_summary_and_count",
]
