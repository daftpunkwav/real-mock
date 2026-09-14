"""Flow-plan generation: background planner call + start-time wait.

Planning runs asynchronously right after session creation; the opening turn
waits (bounded) for the plan and falls back to the static workflow when the
planner failed or timed out — planning problems must never block an interview.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.interview.models import InterviewProcess, InterviewSession
from realmock.domains.interview.services.planning.plan_prompts import (
    build_plan_user_message,
    planner_system_prompt,
)
from realmock.domains.interview.services.planning.plan_schema import (
    InterviewPlan,
    parse_plan,
    plan_from_workflow,
)
from realmock.domains.interview.services.process_memory import (
    load_memory,
    render_for_prompt,
)
from realmock.domains.interview.session_overrides import session_llm
from realmock.domains.interview.services.interview.workflows import get_workflow
from realmock.platform.catalogs.company import get_company_context
from realmock.platform.database import api_db_session, sessions_db_session
from realmock.platform.services.candidate_read import (
    get_resume_agent_payload,
    get_user_profile,
)

logger = logging.getLogger(__name__)

#: Planner call budget; must stay below PLAN_WAIT_TIMEOUT_SECONDS so the
#: opening turn always sees either a ready plan or a failed marker.
PLAN_TIMEOUT_SECONDS = 40.0
#: How long stream_opening waits for the background planner before degrading.
PLAN_WAIT_TIMEOUT_SECONDS = 45.0
_POLL_INTERVAL_SECONDS = 1.0

PLAN_STATUS_PENDING = ""
PLAN_STATUS_READY = "ready"
PLAN_STATUS_FAILED = "failed"


def _process_section(db: Session, session: InterviewSession) -> str:
    """Render prior-round memory for the planner (empty for standalone sessions)."""
    process_id = getattr(session, "process_id", None)
    if not process_id:
        return ""
    process = db.query(InterviewProcess).filter(InterviewProcess.id == process_id).first()
    if process is None:
        return ""
    round_line = (
        f"This is round {session.round_no} of up to {process.max_rounds} "
        f"({process.role} @ {process.company})."
    )
    rendered = render_for_prompt(load_memory(process.memory))
    return round_line + ("\n" + rendered if rendered else "")


def _resume_summary(resume_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(resume_payload, dict):
        return None
    return {
        "skills": resume_payload.get("skills") or [],
        "projects": resume_payload.get("projects") or [],
        "summary": resume_payload.get("summary") or "",
    }


async def generate_plan_for_session(session_id: int) -> None:
    """Background task: plan the interview flow and persist it on the session row.

    Never raises: any failure marks plan_status=failed so the opening turn can
    degrade to the static workflow immediately.
    """
    try:
        with sessions_db_session() as db:
            session = db.get(InterviewSession, session_id)
            if session is None or getattr(session, "plan_status", "") == PLAN_STATUS_READY:
                return
            llm = session_llm(db, session)
            if not llm.api_key:
                session.plan_status = PLAN_STATUS_FAILED
                db.commit()
                return

            with api_db_session() as api_db:
                profile = get_user_profile(api_db, session.profile_id)
                resume_payload = get_resume_agent_payload(api_db, session.resume_id)

            config_like = _config_shim(session)
            user_msg = build_plan_user_message(
                config_like,
                resume_payload=_resume_summary(resume_payload),
                profile=profile,
                process_section=_process_section(db, session),
                company_context=get_company_context(session.company or ""),
            )
            try:
                raw = await asyncio.wait_for(
                    llm.chat_json(
                        [
                            {"role": "system", "content": planner_system_prompt()},
                            {"role": "user", "content": user_msg},
                        ],
                        temperature=0.3,
                    ),
                    timeout=PLAN_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning("plan generation timed out sid=%s", session_id)
                raw = None
            except Exception as e:
                logger.warning("plan generation failed sid=%s: %s", session_id, e)
                raw = None

            plan = parse_plan(raw) if raw else None
            if plan is None:
                session.plan_status = PLAN_STATUS_FAILED
                db.commit()
                return
            session.plan = _dump_plan(plan)
            session.plan_status = PLAN_STATUS_READY
            db.commit()
            logger.info(
                "flow plan ready sid=%s steps=%d", session_id, len(plan.steps)
            )
    except Exception:
        logger.exception("generate_plan_for_session crashed sid=%s", session_id)
        try:
            with sessions_db_session() as db:
                session = db.get(InterviewSession, session_id)
                if session is not None:
                    session.plan_status = PLAN_STATUS_FAILED
                    db.commit()
        except Exception:
            logger.exception("plan failure marking failed sid=%s", session_id)


class _ConfigShim:
    """Attribute view over a session row shaped like InterviewConfig."""

    def __init__(self, session: InterviewSession):
        self.role = session.role
        self.level = session.level
        self.company = session.company
        self.workflow_type = session.workflow_type or "technical"
        self.personality = session.personality or "professional"
        self.strictness = int(session.strictness or 3)
        self.interview_style = session.interview_style or "deep_dive"


def _config_shim(session: InterviewSession) -> _ConfigShim:
    return _ConfigShim(session)


def _dump_plan(plan: InterviewPlan) -> str:
    return json.dumps(plan.to_dict(), ensure_ascii=False)


async def wait_for_plan_ready(
    db: Session, session: InterviewSession, timeout_seconds: float = PLAN_WAIT_TIMEOUT_SECONDS
) -> None:
    """Block (bounded) until the background planner finishes, then reload the row.

    On timeout the caller proceeds with whatever is stored (likely a fallback).
    """
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while getattr(session, "plan_status", "") == PLAN_STATUS_PENDING:
        if asyncio.get_running_loop().time() >= deadline:
            logger.info("plan wait timed out sid=%s", getattr(session, "id", None))
            return
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        db.expire(session)
        db.refresh(session)


def fallback_plan_for(session: InterviewSession) -> InterviewPlan:
    """Static-workflow plan for degraded mode."""
    return plan_from_workflow(get_workflow(session.workflow_type))


async def ensure_plan(db: Session, session: InterviewSession) -> InterviewPlan | None:
    """Wait for the background planner, then guarantee a usable plan.

    - Pending: block (bounded) for the background generation to land.
    - Still no usable plan (failed / timeout / legacy): store the static
      workflow as a fallback plan so the rest of the system only deals with
      plans. Returns None only when even the fallback cannot be stored.
    """
    if getattr(session, "plan_status", PLAN_STATUS_PENDING) == PLAN_STATUS_PENDING:
        await wait_for_plan_ready(db, session)
    existing = parse_plan(getattr(session, "plan", None))
    if existing is not None:
        return existing
    plan = fallback_plan_for(session)
    session.plan = _dump_plan(plan)
    session.plan_status = PLAN_STATUS_READY
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("fallback plan persist failed sid=%s", getattr(session, "id", None))
        return None
    logger.info("fallback plan stored sid=%s steps=%d", getattr(session, "id", None), len(plan.steps))
    return plan


__all__ = [
    "PLAN_STATUS_FAILED",
    "PLAN_STATUS_PENDING",
    "PLAN_STATUS_READY",
    "PLAN_TIMEOUT_SECONDS",
    "PLAN_WAIT_TIMEOUT_SECONDS",
    "ensure_plan",
    "fallback_plan_for",
    "generate_plan_for_session",
    "wait_for_plan_ready",
]
