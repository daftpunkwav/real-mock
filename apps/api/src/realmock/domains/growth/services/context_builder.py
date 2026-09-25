"""Build the growth-analysis context from cross-domain data via platform ports.

Sources (platform layer only — no sibling-domain imports, enforced by the
architecture guard):
- interview sessions + persisted DebriefReport JSON through the session
  catalog port
- resume deep-review summary + profile summary through ``candidate_read``
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from realmock.platform.contracts.session_catalog import get_session_catalog
from realmock.platform.services.candidate_read import (
    format_profile_summary,
    format_resume_analysis_summary,
)

logger = logging.getLogger(__name__)

# Sessions fed to the LLM (newest first). Bounded so the user message stays
# well inside the chat window even with long histories.
DEFAULT_SESSION_LIMIT = 20

# Per-session digest field caps (chars / list lengths) — evidence density
# without flooding the context.
_WEAKNESS_CAP = 3
_STRENGTH_CAP = 2
_PLAN_CAP = 3
_PROBLEM_CAP = 2
_TEXT_CAP = 160


def _as_str_list(raw: Any, cap: int) -> list[str]:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        text = str(item).strip()
        if text:
            out.append(text[:_TEXT_CAP])
        if len(out) >= cap:
            break
    return out


def _session_digest(snapshot: Any) -> dict[str, Any] | None:
    """Compact per-session digest from a session snapshot, or None."""
    try:
        report = json.loads(snapshot.report or "{}")
    except (json.JSONDecodeError, TypeError):
        logger.debug("growth digest: bad report JSON sid=%s", snapshot.id)
        report = {}
    if not isinstance(report, dict) or not report:
        return None
    ended = snapshot.ended_at or snapshot.created_at
    return {
        "session_id": int(snapshot.id or 0),
        "date": ended.strftime("%Y-%m-%d") if ended else "",
        "role": snapshot.role or "",
        "company": snapshot.company or "",
        "level": snapshot.level or "",
        "overall_score": snapshot.overall_score,
        "verdict": report.get("verdict"),
        "score_breakdown": report.get("score_breakdown") or {},
        "weaknesses": _as_str_list(report.get("weaknesses"), _WEAKNESS_CAP),
        "strengths": _as_str_list(report.get("strengths"), _STRENGTH_CAP),
        "training_plan": _as_str_list(report.get("training_plan"), _PLAN_CAP),
        "key_problems": _as_str_list(report.get("key_problems"), _PROBLEM_CAP),
    }


def build_growth_context(
    sessions_db: Session,
    api_db: Session,
    *,
    limit: int = DEFAULT_SESSION_LIMIT,
) -> dict[str, Any]:
    """Aggregate scored sessions + resume + profile into the LLM context dict.

    Returns ``{"sessions": [...], "resume_summary": str, "profile_summary": str}``.
    Sessions with no persisted report are skipped; every failure to read one
    session degrades to skipping it, never raises.
    """
    catalog = get_session_catalog()
    scored = [
        item for item in catalog.list_sessions(sessions_db) if item.overall_score is not None
    ][:max(1, limit)]

    digests: list[dict[str, Any]] = []
    for item in scored:
        try:
            snapshot = catalog.get_session(sessions_db, item.id)
        except Exception:
            logger.warning("growth digest: session load failed sid=%s", item.id, exc_info=True)
            continue
        if snapshot is None:
            continue
        digest = _session_digest(snapshot)
        if digest is not None:
            digests.append(digest)

    return {
        "sessions": digests,
        "resume_summary": format_resume_analysis_summary(api_db),
        "profile_summary": format_profile_summary(api_db),
    }


__all__ = ["DEFAULT_SESSION_LIMIT", "build_growth_context"]
