"""Report routes: get / stream / retry debrief reports."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from realmock.domains.records.schemas.report import DebriefReport, ReportResponse
from realmock.domains.records.services import report_events
from realmock.domains.records.services.debrief_runner import run_debrief_for_session
from realmock.domains.records.services.legacy_fallback import try_legacy_report
from realmock.domains.records.services.report_store import (
    STATUS_FAILED,
    STATUS_GENERATING,
    STATUS_PENDING,
    STATUS_READY,
    get_report_row,
    parse_payload,
    reset_for_retry,
    upsert_pending,
)
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.contracts.session_catalog import (
    SessionSnapshot,
    get_session_catalog,
    snapshot_from_catalog_dict,
)
from realmock.platform.core.constants import DEFAULT_LLM_RATE_LIMIT_PER_MINUTE
from realmock.platform.core.errors import raise_error
from realmock.platform.core.ratelimit import rate_limit_dep
from realmock.platform.core.security import redact_api_key
from realmock.platform.core.sse import format_sse_line, sse_error_event
from realmock.platform.core.session_auth import assert_session_token, extract_token
from realmock.platform.database import get_api_db, get_sessions_db

logger = logging.getLogger(__name__)
router = APIRouter()

_SSE_ERR_GENERIC = "Report generation failed; please retry later"
_PSEUDO_STREAM_CHUNK = 48
_EVENT_POLL_SECONDS = 1.0


async def _generate_with_live_events(
    session_id: int, *, snap, llm, report_out: list
):
    """Run generation as a task, relaying live agent events as SSE.

    The final DebriefReport (or None) is appended to ``report_out`` — async
    generators cannot ``return`` a value.
    """
    queue = report_events.subscribe(session_id)
    try:
        gen_task = asyncio.create_task(
            run_debrief_for_session(
                None,
                None,
                session_id,
                ledger=snap.ledger,
                role=snap.role,
                level=snap.level,
                company=snap.company,
                workflow_type=snap.workflow_type,
                strictness=snap.strictness,
                interview_style=snap.interview_style,
                ended_at=snap.ended_at,
                llm=llm,
                on_event=report_events.publisher(session_id),
            )
        )
        while not gen_task.done():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_EVENT_POLL_SECONDS)
            except asyncio.TimeoutError:
                continue
            yield format_sse_line(event)
        report_out.append(await gen_task)
        while not queue.empty():
            event = queue.get_nowait()
            yield format_sse_line(event)
    finally:
        report_events.unsubscribe(session_id, queue)


def _messages_count(snap: SessionSnapshot) -> int:
    if snap.messages_count:
        return int(snap.messages_count)
    try:
        messages = json.loads(snap.messages or "[]")
    except (ValueError, TypeError):
        logger.debug(
            "Report messages unparsable sid=%s",
            getattr(snap, "session_id", "?"),
            exc_info=True,
        )
        return 0
    if not isinstance(messages, list):
        return 0
    return sum(
        1
        for m in messages
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
    )


def _duration_minutes(snap: SessionSnapshot) -> float | None:
    if snap.duration_seconds is not None:
        return round(float(snap.duration_seconds) / 60, 1)
    if snap.started_at and snap.ended_at:
        delta = snap.ended_at - snap.started_at
        return round(delta.total_seconds() / 60, 1)
    return None


def _require_session(
    db: Session, session_id: int, access: str | None
) -> SessionSnapshot:
    catalog = get_session_catalog()
    raw = catalog.get_session_snapshot(db, session_id)
    if raw is None:
        raise_error("A2001")
    snap = snapshot_from_catalog_dict(raw)
    assert_session_token(snap, access)
    return snap


def _require_finished_session(
    db: Session, session_id: int, access: str | None
) -> SessionSnapshot:
    """Require a finished session (completed status or frozen ledger) for reports."""
    from realmock.platform.core.constants import SessionStatus

    snap = _require_session(db, session_id, access)
    if snap.status == SessionStatus.COMPLETED.value or snap.ledger_frozen:
        return snap
    raise_error("A2003")


def _build_response(
    db: Session,
    snap: SessionSnapshot,
    report: DebriefReport,
    *,
    status: str = STATUS_READY,
) -> ReportResponse:
    catalog = get_session_catalog()
    ledger = snap.ledger
    if ledger is None:
        ledger = catalog.get_ledger(db, snap.id)
    return ReportResponse(
        session_id=snap.id,
        report=report,
        messages_count=_messages_count(snap),
        duration_minutes=_duration_minutes(snap),
        status=status,  # type: ignore[arg-type]
        ledger=ledger,
    )


@router.get("/{session_id}", response_model=ReportResponse)
def get_report(
    session_id: int,
    db: Session = Depends(get_sessions_db),
    access: str | None = Depends(extract_token),
):
    """Return ready; A2004 while pending/generating/absent, A2005 when failed; A2001/A2003 via finished-session guard; legacy fallback if needed."""
    snap = _require_finished_session(db, session_id, access)
    row = get_report_row(db, session_id)
    if row is not None:
        if row.status == STATUS_FAILED:
            raise_error("A2005")
        if row.status in (STATUS_PENDING, STATUS_GENERATING):
            raise_error("A2004")
        if row.status == STATUS_READY:
            report = parse_payload(row)
            if report is None:
                raise_error("A2004")
            return _build_response(db, snap, report, status=STATUS_READY)

    legacy = try_legacy_report(db, session_id)
    if legacy is not None:
        return legacy
    raise_error("A2004")


@router.post("/{session_id}/retry", response_model=ReportResponse)
async def retry_report(
    session_id: int,
    db: Session = Depends(get_sessions_db),
    api_db: Session = Depends(get_api_db),
    access: str | None = Depends(extract_token),
):
    """Re-queue debrief when failed/pending (idempotent). Ready rows are returned as-is."""
    snap = _require_finished_session(db, session_id, access)
    row = reset_for_retry(db, session_id)
    if row.status == STATUS_READY:
        report = parse_payload(row)
        if report is not None:
            return _build_response(db, snap, report)
        raise_error("A2004")
    if row.status == STATUS_GENERATING:
        raise_error("A2004")

    llm = LLMClient.from_db(api_db)
    report = await run_debrief_for_session(
        db,
        api_db,
        session_id,
        ledger=snap.ledger,
        role=snap.role,
        level=snap.level,
        company=snap.company,
        workflow_type=snap.workflow_type,
        strictness=snap.strictness,
        interview_style=snap.interview_style,
        ended_at=snap.ended_at,
        llm=llm,
    )
    if report is None:
        raise_error("A2004")
    return _build_response(db, snap, report)


@router.get(
    "/{session_id}/stream",
    dependencies=[
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
async def get_report_stream(
    session_id: int,
    db: Session = Depends(get_sessions_db),
    api_db: Session = Depends(get_api_db),
    access: str | None = Depends(extract_token),
):
    """Pseudo-stream a ready report; generate once if still pending."""
    snap = _require_finished_session(db, session_id, access)
    llm = LLMClient.from_db(api_db)

    async def event_stream():
        try:
            row = get_report_row(db, session_id)
            report: DebriefReport | None = None
            if row is not None and row.status == STATUS_READY:
                report = parse_payload(row)
            if report is None:
                legacy = try_legacy_report(db, session_id)
                if legacy is not None:
                    report = legacy.report
            if report is None:
                upsert_pending(db, session_id)
                generated: list = []
                async for sse_line in _generate_with_live_events(
                    session_id, snap=snap, llm=llm, report_out=generated
                ):
                    yield sse_line
                report = generated[0] if generated else None
            if report is None:
                # The debrief often outlives the live-event relay (background
                # claim, LLM rounds, web verification). Poll longer before
                # giving up so the SSE stays open on slow generations instead
                # of flashing A2004 while the agent is still working.
                for _i in range(120):
                    await asyncio.sleep(0.5)
                    row2 = get_report_row(db, session_id)
                    if row2 is not None and row2.status == STATUS_READY:
                        report = parse_payload(row2)
                        if report is not None:
                            break
                    if row2 is not None and row2.status == STATUS_FAILED:
                        break
                    # Keep idle connections alive for proxies (~5s heartbeat).
                    if _i % 10 == 9:
                        yield ": ping\n\n"
            if report is None:
                yield format_sse_line(
                    {
                        "type": "error",
                        "message": _SSE_ERR_GENERIC,
                        "code": "A2004",
                        "retryable": True,
                    }
                )
                return

            report_json = report.model_dump_json()
            report_payload = json.loads(report_json)
            for i in range(0, len(report_json), _PSEUDO_STREAM_CHUNK):
                chunk = report_json[i : i + _PSEUDO_STREAM_CHUNK]
                yield format_sse_line({"type": "token", "content": chunk})
            yield format_sse_line({"type": "done", "report": report_payload})
        except asyncio.CancelledError:
            # Client disconnect (navigation, StrictMode remount, timeout) must
            # NOT fail the report: the background debrief task keeps running
            # and persists ready; the next GET/stream polls it up. Marking
            # failed here turned every transient disconnect into a permanent
            # A2005 ("entering detail always errors").
            logger.info("SSE client disconnected sid=%s", session_id)
            raise
        except Exception as e:
            safe_detail = redact_api_key(str(e)) or _SSE_ERR_GENERIC
            logger.exception("stream report failed sid=%s: %s", session_id, safe_detail)
            yield format_sse_line(sse_error_event(e, message=_SSE_ERR_GENERIC, code="C1001"))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
