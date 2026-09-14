"""Multi-round interview process service: lineage, eligibility, round creation.

Owns the business rules for multi-round (round 1..5) processes: when a next round may start,
how finished rounds fold into process memory, and how process status advances.
HTTP handlers stay thin in ``routes/interview/processes.py``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from realmock.domains.interview.constants import InterviewResult, ProcessStatus
from realmock.domains.interview.ledger.store import is_frozen, load_ledger
from realmock.domains.interview.models import InterviewProcess, InterviewSession
from realmock.domains.interview.schemas.process import (
    InterviewProcessResponse,
    ProcessCreateRequest,
    ProcessRoundItem,
    ProcessRoundPlanItem,
)
from realmock.domains.interview.process.process_memory import (
    append_round,
    dump_memory,
    load_memory,
    mark_final,
)
from realmock.domains.interview.process.round_chain import round_chain, step_for
from realmock.domains.interview.process.round_digest import build_round_digest

logger = logging.getLogger(__name__)


class ProcessRoundError(Exception):
    """Raised when a next round cannot be created; ``code`` maps to an API error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def process_rounds(db: Session, process_id: int) -> list[InterviewSession]:
    """All sessions of a process ordered by round_no."""
    return (
        db.query(InterviewSession)
        .filter(InterviewSession.process_id == process_id)
        .order_by(InterviewSession.round_no.asc(), InterviewSession.id.asc())
        .all()
    )


def is_next_round_eligible(
    process: InterviewProcess, rounds: list[InterviewSession]
) -> tuple[bool, int | None]:
    """Next round requires: process active, latest round completed and passed, rounds left.

    Returns (eligible, next_round_no).
    """
    if process.status != ProcessStatus.IN_PROGRESS.value or not rounds:
        return False, None
    latest = rounds[-1]
    if latest.status != "completed" or latest.result != InterviewResult.PASSED.value:
        return False, None
    next_no = (latest.round_no or 0) + 1
    if next_no > process.max_rounds:
        return False, None
    return True, next_no


def _to_response(process: InterviewProcess, rounds: list[InterviewSession]) -> InterviewProcessResponse:
    eligible, next_no = is_next_round_eligible(process, rounds)
    return InterviewProcessResponse(
        id=process.id,
        role=process.role,
        level=process.level,
        company=process.company,
        workflow_type=process.workflow_type,
        max_rounds=process.max_rounds,
        current_round=process.current_round,
        status=process.status,
        next_round_eligible=eligible,
        next_round_no=next_no if eligible else None,
        rounds=[
            ProcessRoundItem(
                session_id=s.id,
                round_no=s.round_no or 0,
                status=s.status,
                result=s.result,
                overall_score=s.overall_score,
                created_at=s.created_at,
            )
            for s in rounds
        ],
        round_plan=[
            ProcessRoundPlanItem(
                round_no=step.round_no,
                kind=step.kind,
                workflow_type=step.workflow_type,
                label=step.label,
                focus=step.focus,
            )
            for step in round_chain(process.workflow_type, process.max_rounds)
        ],
        created_at=process.created_at,
    )


def list_processes(db: Session) -> list[InterviewProcessResponse]:
    """All processes newest-first with round lineage."""
    rows = db.query(InterviewProcess).order_by(InterviewProcess.created_at.desc()).all()
    return [_to_response(p, process_rounds(db, p.id)) for p in rows]


def get_process_detail(db: Session, process_id: int) -> InterviewProcessResponse:
    process = db.query(InterviewProcess).filter(InterviewProcess.id == process_id).first()
    if process is None:
        raise ProcessRoundError("A2001", "Interview process not found")
    return _to_response(process, process_rounds(db, process_id))


def _session_from_process(process: InterviewProcess, round_no: int) -> InterviewSession:
    # Realistic-chain round: each round is a DIFFERENT interviewer type
    # (technical 1 → technical 2 → HR 1 → HR 2 ...), driven by the chain's
    # workflow/personality/style overrides. Falls back to the process defaults
    # when the chain lookup misses (defensive; chains cover the full budget).
    step = step_for(process.workflow_type, round_no, process.max_rounds)
    return InterviewSession(
        profile_id=process.profile_id,
        resume_id=process.resume_id,
        role=process.role,
        level=process.level,
        company=process.company,
        workflow_type=step.workflow_type if step else process.workflow_type,
        personality=step.personality if step else process.personality,
        strictness=step.strictness if step else process.strictness,
        interview_style=step.interview_style if step else process.interview_style,
        avatar_id=process.avatar_id,
        scene_id=process.scene_id,
        status="pending",
        current_phase="identity_check",
        access_token="",
        ai_overrides=process.ai_overrides or "{}",
        process_id=process.id,
        round_no=round_no,
    )


def create_process_with_first_round(
    db: Session, req: ProcessCreateRequest
) -> tuple[InterviewProcess, InterviewSession]:
    """Create a process and its round-1 session in one transaction."""
    process = InterviewProcess(
        resume_id=req.resume_id,
        role=req.role,
        level=req.level,
        company=req.company,
        workflow_type=req.workflow_type,
        personality=req.personality,
        strictness=req.strictness,
        interview_style=req.interview_style,
        avatar_id=req.avatar_id,
        scene_id=req.scene_id,
        # Text column: persist as a JSON string (a raw dict cannot bind on SQLite).
        ai_overrides=(
            json.dumps(req.ai_overrides.model_dump(exclude_none=True), ensure_ascii=False)
            if req.ai_overrides
            else "{}"
        ),
        max_rounds=req.max_rounds,
        current_round=1,
        status=ProcessStatus.IN_PROGRESS.value,
        memory=dump_memory(load_memory(None)),
    )
    db.add(process)
    db.flush()
    # Build the round-1 session only after flush so process.id is assigned.
    session = _session_from_process(process, round_no=1)
    db.add(session)
    db.commit()
    db.refresh(process)
    db.refresh(session)
    return process, session


def create_next_round(db: Session, process_id: int) -> InterviewSession:
    """Create the next session in a process after a passed round.

    Raises :class:`ProcessRoundError` with an API error code when blocked.
    """
    process = db.query(InterviewProcess).filter(InterviewProcess.id == process_id).first()
    if process is None:
        raise ProcessRoundError("A2001", "Interview process not found")
    rounds = process_rounds(db, process_id)
    eligible, next_no = is_next_round_eligible(process, rounds)
    if not eligible or next_no is None:
        raise ProcessRoundError(
            "A2006",
            "No next round available: the latest round must be completed and passed with rounds remaining",
        )
    session = _session_from_process(process, round_no=next_no)
    process.current_round = next_no
    process.updated_at = datetime.now(timezone.utc)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def record_round_finished(db: Session, session: InterviewSession) -> None:
    """Fold a finished round into process memory and advance process status.

    Called from the finish lifecycle; failures are logged, never raised (the
    interview itself is already complete at this point).
    """
    process_id = getattr(session, "process_id", None)
    if not process_id:
        return
    try:
        process = (
            db.query(InterviewProcess).filter(InterviewProcess.id == process_id).first()
        )
        if process is None:
            logger.warning("record_round_finished: process missing pid=%s", process_id)
            return

        memory = load_memory(process.memory)
        ledger = dict(load_ledger(session)) if is_frozen(session) else None
        round_no = session.round_no or 1
        append_round(
            memory,
            round_no=round_no,
            session_id=session.id,
            result=session.result,
            digest=build_round_digest(session, ledger),
        )

        rounds = process_rounds(db, process_id)
        current = max((r.round_no or 0) for r in rounds) if rounds else round_no
        process.current_round = current

        failed = session.result == InterviewResult.FAILED.value
        reached_cap = current >= process.max_rounds
        if failed:
            process.status = ProcessStatus.COMPLETED.value
            mark_final(memory, result=InterviewResult.FAILED.value, rounds_completed=current)
        elif reached_cap and session.result == InterviewResult.PASSED.value:
            process.status = ProcessStatus.COMPLETED.value
            mark_final(memory, result=InterviewResult.PASSED.value, rounds_completed=current)

        process.memory = dump_memory(memory)
        process.updated_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("record_round_finished failed sid=%s", getattr(session, "id", None))


__all__ = [
    "ProcessRoundError",
    "create_next_round",
    "create_process_with_first_round",
    "get_process_detail",
    "is_next_round_eligible",
    "list_processes",
    "process_rounds",
    "record_round_finished",
]
