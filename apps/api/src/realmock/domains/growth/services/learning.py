"""Post-interview system learning memory (local JSON).

Two growth tracks:
1. Candidate growth: GrowthRecord rows (weak skills, training plan)
2. System iteration: local JSON memory (company/role/score aggregates)

This module owns (2). It must not import interview or records domains.
Inputs are duck-typed (Protocol / SimpleNamespace) so callers can pass
ReportSummary-derived data without ORM models.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from realmock.platform.core.file_lock import FileLockTimeout, file_lock

logger = logging.getLogger(__name__)

# In-process serialization (stacked with cross-process file_lock)
_write_lock = threading.Lock()


@runtime_checkable
class LearningSessionLike(Protocol):
    """Minimal session shape for ``record_interview_learning``."""

    id: int
    company: str | None
    role: str | None
    overall_score: int | None
    agent_state: str | dict[str, Any] | None


def _memory_path() -> Path:
    # Same directory as DB: platform/data/
    from realmock.platform.config import PLATFORM_ROOT

    root = PLATFORM_ROOT / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root / "system_learning.json"


def _lock_path() -> Path:
    return _memory_path().with_suffix(".json.lock")


def _default_data() -> dict[str, Any]:
    return {
        "version": 1,
        "followup_category_hits": {},
        "tool_call_counts": {},
        "company_session_counts": {},
        "role_session_counts": {},
        "avg_scores_by_company": {},
        "effective_probes": [],
        "updated_at": None,
    }


def _normalize(data: Any) -> dict[str, Any]:
    """Coerce a loaded snapshot into the expected shape.

    A partially-written or hand-edited file can hold valid JSON of the wrong
    shape (a bare list, string-valued counters, non-dict score entries); left
    as-is it would poison every later read/write with AttributeErrors. Keep
    the well-typed parts, drop the rest, and fill missing keys with defaults.
    """
    if not isinstance(data, dict):
        return _default_data()
    norm = _default_data()
    for key in (
        "followup_category_hits",
        "tool_call_counts",
        "company_session_counts",
        "role_session_counts",
    ):
        raw = data.get(key)
        if isinstance(raw, dict):
            norm[key] = {
                str(k): int(v)
                for k, v in raw.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)
            }
    avgs = data.get("avg_scores_by_company")
    if isinstance(avgs, dict):
        clean: dict[str, dict[str, int]] = {}
        for k, v in avgs.items():
            if (
                isinstance(v, dict)
                and isinstance(v.get("sum"), (int, float))
                and isinstance(v.get("n"), (int, float))
                and not isinstance(v.get("sum"), bool)
                and not isinstance(v.get("n"), bool)
            ):
                clean[str(k)] = {"sum": int(v["sum"]), "n": int(v["n"])}
        norm["avg_scores_by_company"] = clean
    probes = data.get("effective_probes")
    if isinstance(probes, list):
        norm["effective_probes"] = [p for p in probes if isinstance(p, dict)]
    if isinstance(data.get("updated_at"), str):
        norm["updated_at"] = data["updated_at"]
    return norm


def _load_unlocked() -> dict[str, Any]:
    path = _memory_path()
    if not path.exists():
        return _default_data()
    try:
        return _normalize(json.loads(path.read_text(encoding="utf-8")))
    except Exception as e:
        logger.warning("failed to read system_learning: %s", e)
        return _default_data()


def _save_unlocked(data: dict[str, Any]) -> None:
    """Atomic write: temp file + os.replace."""
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = _memory_path()
    tmp = path.with_suffix(".json.tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def _parse_agent_state(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else {}
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def record_interview_learning(
    session: LearningSessionLike,
    *,
    agent_state: dict[str, Any] | None = None,
    report: dict[str, Any] | None = None,
) -> None:
    """Extract system-learnable signals from one completed interview.

    When called from the ReportSummary path, pass ``agent_state=None`` (or empty)
    and put weaknesses in ``report`` — tool/followup stats are skipped without
    ledger/agent_state.
    """
    with _write_lock:
        with file_lock(_lock_path()):
            data = _load_unlocked()
            company = getattr(session, "company", None) or "unknown"
            role = getattr(session, "role", None) or "unknown"
            session_id = int(session.id)

            counts = data.setdefault("company_session_counts", {})
            counts[company] = int(counts.get(company, 0)) + 1

            roles = data.setdefault("role_session_counts", {})
            roles[role] = int(roles.get(role, 0)) + 1

            score = getattr(session, "overall_score", None)
            if score is not None:
                avgs = data.setdefault("avg_scores_by_company", {})
                prev = avgs.get(company) or {"sum": 0, "n": 0}
                prev["sum"] = int(prev.get("sum", 0)) + int(score)
                prev["n"] = int(prev.get("n", 0)) + 1
                avgs[company] = prev

            state = agent_state if agent_state is not None else {}
            if not state:
                state = _parse_agent_state(getattr(session, "agent_state", None))

            # Follow-up category hits (only when agent_state is available)
            cat_hits = data.setdefault("followup_category_hits", {})
            for clue in state.get("followup_clues") or []:
                if isinstance(clue, str) and clue:
                    cat_hits[clue] = int(cat_hits.get(clue, 0)) + 1

            # Tool-call counts (skipped on report-summary path without agent_state)
            tool_counts = data.setdefault("tool_call_counts", {})
            for item in state.get("tool_trace") or []:
                tool = item.get("tool") if isinstance(item, dict) else None
                if tool:
                    tool_counts[tool] = int(tool_counts.get(tool, 0)) + 1

            # Effective probe clues (weak points)
            probes = data.setdefault("effective_probes", [])
            for wp in (state.get("weak_points") or [])[:5]:
                probes.append(
                    {
                        "company": company,
                        "role": role,
                        "point": str(wp)[:200],
                        "session_id": session_id,
                    }
                )

            if report:
                for w in (report.get("weaknesses") or [])[:5]:
                    probes.append(
                        {
                            "company": company,
                            "role": role,
                            "point": str(w)[:200],
                            "session_id": session_id,
                            "source": "report",
                        }
                    )
            # Single truncation after ALL appends keeps the list bounded at
            # 200 no matter which sources contributed this round.
            if len(probes) > 200:
                del probes[:-200]

            _save_unlocked(data)
    logger.info("system learning updated session=%s company=%s", session_id, company)


# Last successfully-read learning snapshot. When the cross-process lock cannot
# be acquired in time, the read path serves this instead of failing the growth
# page (explicit fail-open for a read-only, non-critical aggregate).
_last_snapshot: dict[str, Any] | None = None


def get_system_insights(limit: int = 10) -> dict[str, Any]:
    """System-insight summary for the growth page / API / interview runner.

    Read path is fail-open: if the cross-process file lock cannot be acquired
    within the timeout (a writer holds it across a slow disk), serve the last
    snapshot (or an empty structure on first read) and log a warning instead of
    letting ``FileLockTimeout`` turn into a 500. The summary is advisory input;
    staleness is acceptable, unavailability of the growth page is not.
    """
    global _last_snapshot
    with _write_lock:
        try:
            with file_lock(_lock_path(), timeout=5.0):
                data = _load_unlocked()
        except (FileLockTimeout, OSError):
            logger.warning(
                "system insights read degraded (lock unavailable); serving last snapshot",
                exc_info=True,
            )
            data = _last_snapshot if _last_snapshot is not None else _default_data()
        else:
            _last_snapshot = data
    avgs_raw = data.get("avg_scores_by_company") or {}
    avg_scores = {
        k: round(v["sum"] / v["n"], 1) if v.get("n") else None
        for k, v in avgs_raw.items()
        if isinstance(v, dict)
    }
    cat = data.get("followup_category_hits") or {}
    tools = data.get("tool_call_counts") or {}
    probes = list(data.get("effective_probes") or [])[-limit:]
    return {
        "followup_category_hits": cat,
        "tool_call_counts": tools,
        "company_session_counts": data.get("company_session_counts") or {},
        "role_session_counts": data.get("role_session_counts") or {},
        "avg_scores_by_company": avg_scores,
        "recent_probes": list(reversed(probes)),
        "updated_at": data.get("updated_at"),
    }


__all__ = [
    "LearningSessionLike",
    "get_system_insights",
    "record_interview_learning",
]
