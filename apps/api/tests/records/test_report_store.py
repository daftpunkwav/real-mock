"""Report store tests for src/realmock/domains/records/services/report_store.py.

Covers: pending/ready/failed transitions, stale reclaim, parse, retry reset, aware-time helpers
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from realmock.domains.records.models.report import InterviewReportRow
from realmock.domains.records.schemas.report import DebriefReport
from realmock.domains.records.services import report_store as store


def _report_dict(score=80):
    return {
        "overall_score": score,
        "score_breakdown": {"technical": score, "overall": score},
        "strengths": ["ok"],
        "weaknesses": ["x"],
        "improvement_suggestions": ["y"],
        "turn_notes": [],
    }


def _make_report(score=80) -> DebriefReport:
    return DebriefReport.model_validate(_report_dict(score))


def test_get_report_row_none(db) -> None:
    assert store.get_report_row(db, 999999) is None


def test_upsert_pending_creates(db) -> None:
    row = store.upsert_pending(db, 101)
    assert row.session_id == 101
    assert row.status == store.STATUS_PENDING
    assert store.get_report_row(db, 101) is not None


def test_upsert_pending_ready_unchanged(db) -> None:
    store.persist_ready(db, 102, _make_report())
    row = store.upsert_pending(db, 102)
    assert row.status == store.STATUS_READY


def test_upsert_pending_failed_resets(db) -> None:
    store.upsert_pending(db, 103)
    store.mark_failed(db, 103, "boom")
    row = store.upsert_pending(db, 103)
    assert row.status == store.STATUS_PENDING
    assert row.error_message is None


def test_is_stale_generating_false_for_non_generating(db) -> None:
    row = store.upsert_pending(db, 104)
    assert store.is_stale_generating(row) is False


def test_is_stale_generating_none_updated_is_stale(db) -> None:
    # updated_at=None cannot be committed (NOT NULL); exercise in-memory branch.
    row = InterviewReportRow(session_id=105, status=store.STATUS_GENERATING, updated_at=None)
    assert store.is_stale_generating(row) is True


def test_is_stale_generating_fresh_vs_stale(db) -> None:
    row = store.upsert_pending(db, 106)
    row.status = store.STATUS_GENERATING
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    assert store.is_stale_generating(row) is False
    row.updated_at = datetime.now(timezone.utc) - timedelta(minutes=11)
    db.commit()
    assert store.is_stale_generating(row) is True


def test_reclaim_stale_generating(db) -> None:
    row = store.upsert_pending(db, 107)
    row.status = store.STATUS_GENERATING
    row.updated_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    db.commit()
    out = store.reclaim_stale_generating(db, row)
    assert out.status == store.STATUS_PENDING
    assert "reclaimed" in (out.error_message or "")


def test_upsert_pending_reclaims_stale(db) -> None:
    row = store.upsert_pending(db, 108)
    row.status = store.STATUS_GENERATING
    row.updated_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    db.commit()
    out = store.upsert_pending(db, 108)
    assert out.status == store.STATUS_PENDING


def test_upsert_pending_keeps_fresh_generating(db) -> None:
    row = store.upsert_pending(db, 109)
    row.status = store.STATUS_GENERATING
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    out = store.upsert_pending(db, 109)
    assert out.status == store.STATUS_GENERATING


def test_mark_failed_missing_row_no_crash(db) -> None:
    store.mark_failed(db, 999998, "x")  # no raise


def test_mark_failed_truncates(db) -> None:
    store.upsert_pending(db, 110)
    store.mark_failed(db, 110, "e" * 5000)
    row = store.get_report_row(db, 110)
    assert row is not None and row.status == store.STATUS_FAILED
    assert len(row.error_message or "") == 2000


def test_mark_failed_empty_message_becomes_none(db) -> None:
    store.upsert_pending(db, 111)
    store.mark_failed(db, 111, "")
    assert store.get_report_row(db, 111).error_message is None  # type: ignore[union-attr]


def test_persist_ready_creates_and_updates(db) -> None:
    row = store.persist_ready(db, 112, _make_report(77), model_meta={"source": "t"})
    assert row is not None and row.status == store.STATUS_READY
    assert json.loads(row.model_meta)["source"] == "t"
    parsed = store.parse_payload(row)
    assert parsed is not None and parsed.overall_score == 77
    # Update existing
    row2 = store.persist_ready(db, 112, _make_report(88))
    assert store.parse_payload(row2).overall_score == 88  # type: ignore[union-attr]


def test_parse_payload_empty_and_invalid(db) -> None:
    row = store.upsert_pending(db, 113)
    assert store.parse_payload(row) is None
    row.payload = "not-json"
    db.commit()
    assert store.parse_payload(row) is None
    row.payload = json.dumps({"overall_score": "bad-shape-but-validated-with-defaults"})
    db.commit()
    # Pydantic coerces/defaults; must not crash (None or report)
    assert store.parse_payload(row) is None or isinstance(store.parse_payload(row), DebriefReport)


def test_reset_for_retry_creates_when_missing(db) -> None:
    row = store.reset_for_retry(db, 114)
    assert row.status == store.STATUS_PENDING


def test_reset_for_retry_ready_unchanged(db) -> None:
    store.persist_ready(db, 115, _make_report())
    row = store.reset_for_retry(db, 115)
    assert row.status == store.STATUS_READY


def test_reset_for_retry_fresh_generating_unchanged(db) -> None:
    row = store.upsert_pending(db, 116)
    row.status = store.STATUS_GENERATING
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    out = store.reset_for_retry(db, 116)
    assert out.status == store.STATUS_GENERATING


def test_reset_for_retry_failed_and_stale_reset(db) -> None:
    store.upsert_pending(db, 117)
    store.mark_failed(db, 117, "boom")
    assert store.reset_for_retry(db, 117).status == store.STATUS_PENDING
    row = store.upsert_pending(db, 118)
    row.status = store.STATUS_GENERATING
    row.updated_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    db.commit()
    assert store.reset_for_retry(db, 118).status == store.STATUS_PENDING


def test_as_aware_naive_and_aware() -> None:
    naive = datetime(2024, 1, 1, 12, 0, 0)
    out = store._as_aware(naive)
    assert out is not None and out.tzinfo is not None
    aware = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert store._as_aware(aware) == aware
    assert store._as_aware(None) is None


def test_utcnow_is_aware() -> None:
    assert store._utcnow().tzinfo is not None


@pytest.mark.asyncio
async def test_report_row_unique_session(db) -> None:
    store.upsert_pending(db, 119)
    again = store.upsert_pending(db, 119)
    assert again.session_id == 119
    rows = db.query(InterviewReportRow).filter(InterviewReportRow.session_id == 119).all()
    assert len(rows) == 1
