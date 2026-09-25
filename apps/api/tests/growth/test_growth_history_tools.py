"""Growth history agent-tool tests (list_sessions / get_report handlers).

The handlers resolve the session catalog at call time, so the catalog patch
must span the execution, not just the spec construction.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from realmock.domains.growth.agents.tools import (
    REPORT_OBSERVATION_MAX_CHARS,
    history_tool_specs,
)
from realmock.platform.capabilities.ai.agent.tools.spec import ToolBundle


def _run(coro):
    return asyncio.run(coro)


def _snapshot(
    sid: int,
    score: int | None,
    *,
    report: str | None = None,
    result: str = "passed",
) -> MagicMock:
    snap = MagicMock()
    snap.id = sid
    snap.role = "后端"
    snap.company = "ACME"
    snap.level = "mid"
    snap.round_no = 1
    snap.overall_score = score
    snap.result = result
    when = datetime(2026, 9, 1, tzinfo=timezone.utc)
    snap.ended_at = when
    snap.created_at = when
    snap.report = report if report is not None else json.dumps({"verdict": result})
    return snap


def _catalog(sessions, snapshots: dict[int, MagicMock] | None = None) -> MagicMock:
    catalog = MagicMock()
    catalog.list_sessions.return_value = sessions
    catalog.get_session.side_effect = lambda db, sid: (snapshots or {}).get(sid)
    return catalog


def _run_tool(catalog: MagicMock, name: str, args: dict) -> str:
    bundle = ToolBundle()
    with patch(
        "realmock.domains.growth.agents.tools.get_session_catalog",
        return_value=catalog,
    ):
        bundle.extend(history_tool_specs(MagicMock()))
        return _run(bundle.execute(name, args))


def test_specs_register_two_history_tools() -> None:
    bundle = ToolBundle()
    bundle.extend(history_tool_specs(MagicMock()))
    assert bundle.names() == frozenset({"history_list_sessions", "history_get_report"})
    get_report = bundle.definitions()[1]["function"]
    assert get_report["parameters"]["required"] == ["session_id"]


def test_list_sessions_shapes_rows_and_drops_unscored() -> None:
    catalog = _catalog([_snapshot(2, 72), _snapshot(3, None)])
    body = json.loads(_run_tool(catalog, "history_list_sessions", {}))
    assert body["count"] == 1
    row = body["sessions"][0]
    assert row["session_id"] == 2
    assert row["date"] == "2026-09-01"
    assert row["overall_score"] == 72
    assert row["verdict"] == "passed"
    assert row["round_no"] == 1


def test_list_sessions_limit_accepts_numbers_only() -> None:
    sessions = [_snapshot(i, 60) for i in range(5)]
    catalog = _catalog(sessions)
    assert len(json.loads(_run_tool(catalog, "history_list_sessions", {"limit": 2}))["sessions"]) == 2
    assert len(json.loads(_run_tool(catalog, "history_list_sessions", {"limit": 2.0}))["sessions"]) == 2
    # Non-numeric limit falls back to the default page size.
    assert len(json.loads(_run_tool(catalog, "history_list_sessions", {"limit": "many"}))["sessions"]) == 5


def test_get_report_rejects_invalid_session_id() -> None:
    catalog = _catalog([])
    for bad in (None, [], ["1"], "abc"):
        body = json.loads(_run_tool(catalog, "history_get_report", {"session_id": bad}))
        assert body == {"error": "invalid_session_id"}


def test_get_report_unknown_or_unscored_session() -> None:
    catalog = _catalog([], snapshots={7: None, 8: _snapshot(8, None)})
    body = json.loads(_run_tool(catalog, "history_get_report", {"session_id": 7}))
    assert body == {"error": "session_not_found", "session_id": 7}
    body = json.loads(_run_tool(catalog, "history_get_report", {"session_id": 8}))
    assert body == {"error": "session_not_scored", "session_id": 8}


def test_get_report_degrades_corrupt_or_empty_report() -> None:
    catalog = _catalog(
        [],
        snapshots={
            9: _snapshot(9, 60, report="{not json"),
            10: _snapshot(10, 60, report="{}"),
        },
    )
    for sid in (9, 10):
        body = json.loads(_run_tool(catalog, "history_get_report", {"session_id": sid}))
        assert body == {"error": "report_unavailable", "session_id": sid}


def test_get_report_returns_full_envelope() -> None:
    snapshot = _snapshot(11, 66, report=json.dumps({"verdict": "passed", "score": 66}))
    catalog = _catalog([snapshot], snapshots={11: snapshot})
    body = json.loads(_run_tool(catalog, "history_get_report", {"session_id": "11"}))
    assert body["session_id"] == 11
    assert body["overall_score"] == 66
    assert body["report"] == {"verdict": "passed", "score": 66}
    assert body["company"] == "ACME"


def test_get_report_truncates_oversized_report() -> None:
    report = json.dumps({"weaknesses": ["w" * (REPORT_OBSERVATION_MAX_CHARS + 500)]})
    snapshot = _snapshot(12, 60, report=report)
    catalog = _catalog([snapshot], snapshots={12: snapshot})
    raw = _run_tool(catalog, "history_get_report", {"session_id": 12})
    assert len(raw) < len(report)
    assert "chunk truncated" in raw
