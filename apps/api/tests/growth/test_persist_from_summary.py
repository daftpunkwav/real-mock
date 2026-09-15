"""Persist from summary tests for src/realmock/domains/growth/services/persist_from_summary.py.

Covers: create/idempotent/default-profile/truncate/race/rollback branches
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from realmock.domains.growth.models.growth import GrowthRecord
from realmock.domains.growth.services.persist_from_summary import (
    persist_growth_from_summary,
)
from realmock.platform.contracts.report_summary import ReportSummaryPayload
from realmock.platform.core.ratelimit import reset_rate_limit
from sqlalchemy.exc import IntegrityError


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


@pytest.fixture(autouse=True)
def _growth_table(engine):
    from realmock.platform.database import SessionsBase
    import realmock.domains.growth.models.growth  # noqa: F401

    SessionsBase.metadata.create_all(bind=engine)
    yield


def _payload(sid=601, profile_id=3) -> ReportSummaryPayload:
    return ReportSummaryPayload(
        session_id=sid,
        profile_id=profile_id,
        overall_score=80,
        score_breakdown={"overall": 80},
        weaknesses=["cache", "index"],
        training_plan=["drill cache"],
    )


def test_persist_creates_row(db) -> None:
    row, created = persist_growth_from_summary(db, _payload(601))
    assert created is True
    assert row is not None and row.session_id == 601
    assert json.loads(row.weak_skills) == ["cache", "index"]
    assert json.loads(row.common_mistakes) == ["cache", "index"]
    assert json.loads(row.training_plan) == ["drill cache"]


def test_persist_idempotent_skip(db) -> None:
    first, created = persist_growth_from_summary(db, _payload(602))
    assert created is True
    second, created2 = persist_growth_from_summary(db, _payload(602))
    assert created2 is False
    assert second.id == first.id
    assert len(db.query(GrowthRecord).filter(GrowthRecord.session_id == 602).all()) == 1


def test_persist_missing_profile_defaults_to_1(db) -> None:
    row, created = persist_growth_from_summary(db, _payload(603, profile_id=None))
    assert created is True
    assert row is not None and row.profile_id == 1


def test_persist_truncates_weaknesses_for_mistakes(db) -> None:
    payload = ReportSummaryPayload(
        session_id=604,
        profile_id=1,
        weaknesses=["w1", "w2", "w3", "w4"],
        training_plan=[],
    )
    row, _ = persist_growth_from_summary(db, payload)
    assert row is not None
    assert json.loads(row.common_mistakes) == ["w1", "w2", "w3"]


def test_persist_race_branch_with_mocks() -> None:
    db = MagicMock()
    existing = MagicMock()
    # First query -> None (miss), second query -> existing row.
    q = MagicMock()
    q.filter.return_value.order_by.return_value.first.side_effect = [None, existing]
    db.query.return_value = q
    db.commit.side_effect = IntegrityError("stmt", "params", Exception("dup"))
    row, created = persist_growth_from_summary(db, _payload(606))
    assert created is False
    assert row is existing
    db.rollback.assert_called()


def test_persist_generic_failure_rolls_back_and_raises(db) -> None:
    with patch.object(db, "commit", side_effect=RuntimeError("db down")):
        with pytest.raises(RuntimeError):
            persist_growth_from_summary(db, _payload(607))
