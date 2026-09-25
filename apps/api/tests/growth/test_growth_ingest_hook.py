"""Growth ingest-hook tests (report summary triggers insight regen)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _payload(sid: int):
    from realmock.platform.contracts.report_summary import ReportSummaryPayload

    return ReportSummaryPayload(session_id=sid, overall_score=80)


def test_ingest_schedules_regen_on_create() -> None:
    from realmock.domains.growth.services import ingest as mod

    with (
        patch.object(mod, "persist_growth_from_summary", return_value=(MagicMock(), True)),
        patch.object(mod, "record_interview_learning"),
        patch.object(mod, "schedule_growth_insight_regen") as sched,
    ):
        mod.handle_report_summary(_payload(9201))
        sched.assert_called_once()


def test_ingest_no_regen_when_not_created() -> None:
    from realmock.domains.growth.services import ingest as mod

    with (
        patch.object(mod, "persist_growth_from_summary", return_value=(MagicMock(), False)),
        patch.object(mod, "schedule_growth_insight_regen") as sched,
    ):
        mod.handle_report_summary(_payload(9202))
        sched.assert_not_called()


def test_ingest_regen_schedule_failure_swallowed() -> None:
    from realmock.domains.growth.services import ingest as mod

    with (
        patch.object(mod, "persist_growth_from_summary", return_value=(MagicMock(), True)),
        patch.object(mod, "record_interview_learning"),
        patch.object(mod, "schedule_growth_insight_regen", side_effect=RuntimeError("no loop")),
    ):
        mod.handle_report_summary(_payload(9203))  # must not raise
