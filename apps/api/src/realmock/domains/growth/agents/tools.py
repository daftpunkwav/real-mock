"""Reusable interview-history Agent tools for the growth agent.

Wraps the session-catalog platform port so the growth agent can page through
finished, scored interview sessions on demand. This module must not import
sibling domain packages — the catalog port is registered at the composition
root (see ``bootstrap``).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from realmock.platform.capabilities.ai.agent.tools.spec import ToolSpec
from realmock.platform.capabilities.ai.llm.json_extract import truncate_chunk
from realmock.platform.contracts.session_catalog import get_session_catalog

# Attention bound (not a context-space bound): a full DebriefReport can be
# large, so one observation is capped head+tail with an explicit elision
# marker — same policy as the resume-review loop.
REPORT_OBSERVATION_MAX_CHARS = 16_000
_LIST_DEFAULT_LIMIT = 20


def history_tool_specs(sessions_db: Session) -> list[ToolSpec]:
    """Bind interview-history tools to one sessions-db session."""

    def _scored_items(limit: int):
        catalog = get_session_catalog()
        items = [i for i in catalog.list_sessions(sessions_db) if i.overall_score is not None]
        return items[: max(1, limit)]

    async def list_sessions(args: dict[str, Any]) -> str:
        limit = args.get("limit")
        rows = []
        for item in _scored_items(
            int(limit) if isinstance(limit, (int, float)) else _LIST_DEFAULT_LIMIT
        ):
            ended = item.ended_at or item.created_at
            rows.append(
                {
                    "session_id": int(item.id) if item.id is not None else 0,
                    "date": ended.strftime("%Y-%m-%d") if ended else "",
                    "role": item.role or "",
                    "company": item.company or "",
                    "level": item.level or "",
                    "overall_score": item.overall_score,
                    "verdict": item.result,
                    "round_no": item.round_no,
                }
            )
        return json.dumps({"count": len(rows), "sessions": rows}, ensure_ascii=False)

    async def get_report(args: dict[str, Any]) -> str:
        raw_sid = args.get("session_id")
        if not isinstance(raw_sid, (int, str)):
            return json.dumps({"error": "invalid_session_id"}, ensure_ascii=False)
        try:
            sid = int(raw_sid)
        except (TypeError, ValueError):
            return json.dumps({"error": "invalid_session_id"}, ensure_ascii=False)
        catalog = get_session_catalog()
        snapshot = catalog.get_session(sessions_db, sid)
        if snapshot is None:
            return json.dumps({"error": "session_not_found", "session_id": sid}, ensure_ascii=False)
        if snapshot.overall_score is None:
            return json.dumps(
                {"error": "session_not_scored", "session_id": sid}, ensure_ascii=False
            )
        try:
            report = json.loads(snapshot.report or "{}")
        except (json.JSONDecodeError, TypeError):
            report = {}
        if not isinstance(report, dict) or not report:
            return json.dumps(
                {"error": "report_unavailable", "session_id": sid}, ensure_ascii=False
            )
        ended = snapshot.ended_at or snapshot.created_at
        envelope = {
            "session_id": sid,
            "date": ended.strftime("%Y-%m-%d") if ended else "",
            "role": snapshot.role or "",
            "company": snapshot.company or "",
            "level": snapshot.level or "",
            "overall_score": snapshot.overall_score,
            "result": snapshot.result,
            "report": report,
        }
        body = json.dumps(envelope, ensure_ascii=False)
        return truncate_chunk(body, limit=REPORT_OBSERVATION_MAX_CHARS)

    return [
        ToolSpec(
            name="history_list_sessions",
            description=(
                "List finished, scored mock-interview sessions (newest first) with "
                "id/date/role/company/overall_score/verdict. Call this first to see "
                "the candidate's history, then fetch individual reports."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max sessions to return (default 20)",
                    },
                },
                "required": [],
            },
            handler=list_sessions,
        ),
        ToolSpec(
            name="history_get_report",
            description=(
                "Read one session's full interview report by session_id: overall "
                "score, verdict + reasoning, dimension score breakdown, strengths, "
                "weaknesses, key problems, training plan, and phase summary."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "integer",
                        "description": "Session id from history_list_sessions",
                    },
                },
                "required": ["session_id"],
            },
            handler=get_report,
        ),
    ]


__all__ = ["REPORT_OBSERVATION_MAX_CHARS", "history_tool_specs"]
