"""Growth ingest tests for src/realmock/domains/growth/services/ingest.py.

Covers: persist-failure/skip-not-created/learning-failure/handler-wiring
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from realmock.platform.core.ratelimit import reset_rate_limit


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


# ---- routes/router (59-67, 73-74) ----








# ---- ingest (29-31, 34-35, 50-51) ----


def test_ingest_persist_failure_returns() -> None:
    from realmock.domains.growth.services import ingest as mod
    from realmock.platform.contracts.report_summary import ReportSummaryPayload

    payload = ReportSummaryPayload(session_id=9101, overall_score=80)
    with patch.object(
        mod, "persist_growth_from_summary", side_effect=RuntimeError("db down")
    ):
        mod.handle_report_summary(payload)


def test_ingest_skip_when_not_created() -> None:
    from realmock.domains.growth.services import ingest as mod
    from realmock.platform.contracts.report_summary import ReportSummaryPayload

    payload = ReportSummaryPayload(session_id=9102, overall_score=80)
    with (
        patch.object(mod, "persist_growth_from_summary", return_value=(MagicMock(), False)),
        patch.object(mod, "record_interview_learning") as learn,
    ):
        mod.handle_report_summary(payload)
        learn.assert_not_called()


def test_ingest_learning_failure_logged() -> None:
    from realmock.domains.growth.services import ingest as mod
    from realmock.platform.contracts.report_summary import ReportSummaryPayload

    payload = ReportSummaryPayload(session_id=9103, overall_score=80)
    with (
        patch.object(mod, "persist_growth_from_summary", return_value=(MagicMock(), True)),
        patch.object(mod, "record_interview_learning", side_effect=RuntimeError("learn down")),
    ):
        mod.handle_report_summary(payload)


def test_register_handlers_wires_hook() -> None:
    from realmock.domains.growth.services import ingest as mod

    mod.register_growth_lifecycle_handlers()
    from realmock.platform.contracts.lifecycle_hooks import get_on_report_summary

    assert get_on_report_summary() is mod.handle_report_summary


# ---- learning (73-75, 90, 96-97) ----


