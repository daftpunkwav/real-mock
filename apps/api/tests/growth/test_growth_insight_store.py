"""Growth insight persistence tests (upsert / degrade / read shape)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError


def test_store_upsert_and_get(insight_table) -> None:
    from realmock.domains.growth.services.insight_store import (
        upsert_insight,
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    first = upsert_insight(db, {"headline": "v1"}, locale="zh-CN", session_count=3)
    assert first is not None
    db.add.assert_called_once()


def test_store_upsert_retries_as_update_after_integrity_race() -> None:
    """A unique-constraint race retries as an update on the winner's row."""
    from realmock.domains.growth.services.insight_store import upsert_insight
    from sqlalchemy.exc import IntegrityError

    db = MagicMock()
    raced_row = MagicMock()
    # 1st read -> nothing stored (insert branch); 2nd read -> the concurrent
    # winner's row is now visible after the rollback.
    db.query.return_value.filter.return_value.order_by.return_value.first.side_effect = [
        None,
        raced_row,
    ]
    db.commit.side_effect = [IntegrityError("ux", None, Exception("unique")), None]

    out = upsert_insight(db, {"headline": "v2"}, locale="en", session_count=1)

    assert out is raced_row
    assert raced_row.payload == json.dumps({"headline": "v2"}, ensure_ascii=False)
    assert raced_row.locale == "en"
    assert raced_row.session_count == 1
    assert db.commit.call_count == 2
    db.rollback.assert_called_once()


def test_store_upsert_race_raises_when_winner_row_vanishes() -> None:
    """If the retry read still finds no row, the race error must surface."""
    from realmock.domains.growth.services.insight_store import upsert_insight
    from sqlalchemy.exc import IntegrityError

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    db.commit.side_effect = IntegrityError("ux", None, Exception("unique"))

    with pytest.raises(IntegrityError):
        upsert_insight(db, {"headline": "v"}, locale="en", session_count=1)


def test_get_latest_insight_tolerates_missing_table() -> None:
    """A missing table (fresh/partial DB) reads as no insight, not a crash."""
    from realmock.domains.growth.services.insight_store import get_latest_insight

    db = MagicMock()
    db.query.side_effect = OperationalError("no table", None, Exception("missing"))

    assert get_latest_insight(db) is None
    db.rollback.assert_called_once()


def test_insight_response_null_and_payload() -> None:
    from realmock.domains.growth.services.insight_store import insight_response

    assert insight_response(None) == {"insight": None}
    row = MagicMock()
    row.payload = json.dumps({"headline": "h"})
    row.updated_at = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
    row.session_count = 5
    row.locale = "zh-CN"
    body = insight_response(row)
    assert body["insight"]["headline"] == "h"
    assert body["insight"]["session_count"] == 5


def test_insight_response_tolerates_non_object_payload() -> None:
    """Valid JSON that is not an object must degrade to empty, not raise.

    A stored "[]" or "null" parses fine, so the JSONDecodeError guard does not
    fire; spreading a non-mapping would raise TypeError and 500 the GET route.
    """
    from realmock.domains.growth.services.insight_store import insight_response

    row = MagicMock()
    row.updated_at = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
    row.session_count = 0
    row.locale = "zh-CN"
    for raw in ("[]", "null", '"text"', "3"):
        row.payload = raw
        body = insight_response(row)
        assert body["insight"]["generated_at"] is not None
        assert body["insight"]["session_count"] == 0


def test_insight_response_degrades_corrupt_json() -> None:
    """Unparseable stored JSON yields the envelope with no payload fields."""
    from realmock.domains.growth.services.insight_store import insight_response

    row = MagicMock()
    row.payload = "{not json"
    row.updated_at = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
    row.session_count = 4
    row.locale = "en"
    body = insight_response(row)
    assert "headline" not in body["insight"]
    assert body["insight"]["session_count"] == 4
