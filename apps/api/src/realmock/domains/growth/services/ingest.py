"""Ingest ReportSummaryPayload into growth (persist + system learning)."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from realmock.domains.growth.services.insight_scheduler import schedule_growth_insight_regen
from realmock.domains.growth.services.learning import record_interview_learning
from realmock.domains.growth.services.persist_from_summary import persist_growth_from_summary
from realmock.platform.contracts.lifecycle_hooks import set_on_report_summary
from realmock.platform.contracts.report_summary import ReportSummaryPayload
from realmock.platform.database import sessions_db_session

logger = logging.getLogger(__name__)


def handle_report_summary(payload: ReportSummaryPayload) -> None:
    """Persist GrowthRecord and update system learning from a report summary.

    Does not read ledger/messages/tool results — only summary fields.
    Learning runs only when a new GrowthRecord is created (idempotent).
    Failures are logged; this handler must not crash the records path.
    """
    sid = int(payload.session_id)
    created = False
    try:
        with sessions_db_session() as db:
            _row, created = persist_growth_from_summary(db, payload)
    except Exception:
        logger.exception("growth persist failed sid=%s (summary path unaffected)", sid)
        return

    if not created:
        logger.info("growth learning skip sid=%s (record already existed)", sid)
        return

    try:
        session_like = SimpleNamespace(
            id=sid,
            company=payload.company,
            role=payload.role,
            overall_score=payload.overall_score,
            agent_state=None,
        )
        record_interview_learning(
            session_like,
            agent_state={},
            report={"weaknesses": list(payload.weaknesses or [])},
        )
    except Exception:
        logger.exception("growth learning failed sid=%s", sid)

    # A new scored session changes the cross-session picture: regenerate the
    # LLM growth insight in the background (single-flight, failures logged).
    try:
        schedule_growth_insight_regen()
    except Exception:
        logger.exception("growth insight regen scheduling failed sid=%s", sid)


def register_growth_lifecycle_handlers() -> None:
    """Wire growth ingest into the platform report-summary hook."""
    set_on_report_summary(handle_report_summary)


__all__ = ["handle_report_summary", "register_growth_lifecycle_handlers"]
