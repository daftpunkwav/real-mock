"""Growth insight session-index tests (the agent's compact input)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


def test_build_session_index_keeps_scored_only() -> None:
    from realmock.domains.growth.agents.insight import _build_session_index

    unscored = MagicMock(id=3, overall_score=None)
    scored = MagicMock(
        id=2,
        overall_score=70,
        role="后端",
        company="ACME",
        level="mid",
        result="passed",
        ended_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        created_at=None,
    )
    catalog = MagicMock()
    catalog.list_sessions.return_value = [scored, unscored]

    with patch(
        "realmock.domains.growth.agents.insight.get_session_catalog",
        return_value=catalog,
    ):
        index = _build_session_index(MagicMock())

    assert len(index) == 1
    assert index[0]["session_id"] == 2
    assert index[0]["date"] == "2026-09-01"
    assert index[0]["overall_score"] == 70


def test_build_session_index_respects_limit() -> None:
    from realmock.domains.growth.agents.insight import _build_session_index

    rows = [
        MagicMock(
            id=i,
            overall_score=60,
            role="r",
            company="c",
            level="l",
            result="passed",
            ended_at=None,
            created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
        for i in range(10)
    ]
    catalog = MagicMock()
    catalog.list_sessions.return_value = rows

    with patch(
        "realmock.domains.growth.agents.insight.get_session_catalog",
        return_value=catalog,
    ):
        assert len(_build_session_index(MagicMock(), limit=3)) == 3
