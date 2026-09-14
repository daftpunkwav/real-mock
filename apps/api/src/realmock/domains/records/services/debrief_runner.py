"""CAS-like deep report runner: claim -> ReAct agent (no DB pin) -> persist -> notify.

HTTP and ingest paths both use short-lived DB sessions around claim/persist so
the agent awaits never hold a SQLite connection. Generation is delegated to
the records-domain ReAct report agent (stage 1 turn notes + stage 2 synthesis).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import update
from sqlalchemy.orm import Session

from realmock.domains.records.agents.report import DeepReportAgent
from realmock.domains.records.models.report import InterviewReportRow
from realmock.domains.records.schemas.report import DebriefReport
from realmock.domains.records.services.report_store import (
    STATUS_FAILED,
    STATUS_GENERATING,
    STATUS_PENDING,
    STATUS_READY,
    get_report_row,
    is_stale_generating,
    mark_failed,
    parse_payload,
    persist_ready,
    reclaim_stale_generating,
)
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.contracts.lifecycle_hooks import notify_report_summary
from realmock.platform.contracts.report_summary import ReportSummaryPayload
from realmock.platform.contracts.session_catalog import (
    get_session_catalog,
    snapshot_from_catalog_dict,
)
from realmock.platform.contracts.session_score import apply_session_overall_score
from realmock.platform.database import api_db_session, sessions_db_session

logger = logging.getLogger(__name__)

OnEvent = Callable[[dict], Awaitable[None]]


def try_claim_generation(db: Session, session_id: int) -> bool:
    """CAS: pending|failed|(stale generating) -> generating."""
    row = get_report_row(db, session_id)
    if row is not None and row.status == STATUS_GENERATING and is_stale_generating(row):
        reclaim_stale_generating(db, row)
    try:
        result = db.execute(
            update(InterviewReportRow)
            .where(InterviewReportRow.session_id == session_id)
            .where(InterviewReportRow.status.in_([STATUS_PENDING, STATUS_FAILED]))
            .values(
                status=STATUS_GENERATING,
                error_message=None,
                updated_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        return (getattr(result, "rowcount", 0) or 0) > 0
    except Exception:
        db.rollback()
        logger.debug("debrief CAS claim failed sid=%s", session_id, exc_info=True)
        return False


def _build_summary(
    session_id: int,
    report: DebriefReport,
    *,
    profile_id: int | None = None,
    company: str = "",
    role: str = "",
    ended_at: datetime | None = None,
) -> ReportSummaryPayload:
    digest: list[str] = []
    for note in report.turn_notes[:20]:
        summary = (note.user_review.summary or note.answer_summary or "").strip()
        if summary:
            digest.append(f"{note.turn_id}: {summary[:120]}")
    return ReportSummaryPayload(
        session_id=session_id,
        profile_id=profile_id,
        overall_score=report.overall_score,
        score_breakdown=report.score_breakdown.model_dump(),
        weaknesses=list(report.weaknesses or []),
        training_plan=list(report.training_plan or []),
        turn_note_digest=digest,
        company=company,
        role=role,
        ended_at=ended_at,
    )


async def run_debrief_for_session(
    db: Session | None,
    api_db: Session | None,
    session_id: int,
    *,
    ledger: dict[str, Any] | None = None,
    role: str = "",
    level: str = "",
    company: str = "",
    workflow_type: str = "technical",
    strictness: int = 3,
    interview_style: str = "deep_dive",
    ended_at: datetime | None = None,
    llm: LLMClient | None = None,
    on_event: OnEvent | None = None,
) -> DebriefReport | None:
    """Claim and run the deep report without pinning DB across agent awaits.

    ``db`` / ``api_db`` are accepted for call-site compatibility but claim/persist
    always use owned short sessions. Failures mark the row failed and return None.
    """
    del db, api_db
    return await _run_with_owned_sessions(
        session_id,
        ledger=ledger,
        role=role,
        level=level,
        company=company,
        workflow_type=workflow_type,
        strictness=strictness,
        interview_style=interview_style,
        ended_at=ended_at,
        llm=llm,
        on_event=on_event,
    )


async def _run_with_owned_sessions(
    session_id: int,
    *,
    ledger: dict[str, Any] | None,
    role: str,
    level: str,
    company: str,
    workflow_type: str,
    strictness: int,
    interview_style: str,
    ended_at: datetime | None,
    llm: LLMClient | None,
    on_event: OnEvent | None,
) -> DebriefReport | None:
    """Claim+meta in short sessions, agent without DB, then persist."""
    profile_id: int | None = None
    resume_id: int | None = None
    process_id: int | None = None
    session_result: str | None = None
    with sessions_db_session() as db:
        row = get_report_row(db, session_id)
        if row is None:
            return None
        if row.status == STATUS_READY:
            return parse_payload(row)
        if row.status == STATUS_GENERATING and not is_stale_generating(row):
            return None
        if not try_claim_generation(db, session_id):
            return None
        catalog = get_session_catalog()
        raw = catalog.get_session_snapshot(db, session_id)
        if raw is not None:
            snap = snapshot_from_catalog_dict(raw)
            role = role or snap.role
            level = level or snap.level
            company = company or snap.company
            workflow_type = workflow_type or snap.workflow_type
            strictness = strictness or snap.strictness
            interview_style = interview_style or snap.interview_style
            ended_at = ended_at or snap.ended_at
            profile_id = snap.profile_id
            resume_id = snap.resume_id
            session_result = snap.result
            process_id = snap.process_id
            if ledger is None and snap.ledger is not None:
                ledger = snap.ledger
        process_context = (
            catalog.get_process_context(db, process_id) if process_id else ""
        )

    try:
        if llm is not None:
            client = llm
        else:
            with api_db_session() as fresh_api:
                client = LLMClient.from_db(fresh_api)

        report = await DeepReportAgent(llm=client, on_event=on_event).run(
            role=role,
            level=level,
            company=company,
            workflow_type=workflow_type,
            strictness=strictness,
            interview_style=interview_style,
            ledger=ledger or {},
            session_result=session_result,
            process_context=process_context,
            resume_id=resume_id,
            profile_id=profile_id,
        )

        with sessions_db_session() as db:
            persist_ready(
                db,
                session_id,
                report,
                model_meta={
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "source": "records.debrief",
                },
            )
            try:
                apply_session_overall_score(db, session_id, int(report.overall_score))
            except Exception:
                logger.exception(
                    "overall_score projection failed sid=%s (report already ready)",
                    session_id,
                )

        await notify_report_summary(
            _build_summary(
                session_id,
                report,
                profile_id=profile_id,
                company=company,
                role=role,
                ended_at=ended_at,
            )
        )
        return report
    except Exception as exc:
        logger.exception("debrief failed sid=%s", session_id)
        with sessions_db_session() as db:
            mark_failed(db, session_id, str(exc))
        return None
