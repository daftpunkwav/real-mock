"""HR round-program generation: background planner call + degraded static chain.

Mirrors :mod:`planning.planner`: planning runs asynchronously right after
process creation; round creation and process views use the LLM-authored
program when ready and degrade to the static :func:`round_chain` otherwise —
planning problems must never block an interview loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from realmock.domains.interview.agents import session_llm
from realmock.domains.interview.models import InterviewProcess, InterviewSession
from realmock.domains.interview.agents.research.company_research import (
    blend_company_context,
    needs_company_research,
    research_company_context,
)
from realmock.domains.interview.agents.planning.round_plan_prompts import (
    build_round_plan_user_message,
    hr_planner_system_prompt,
)
from realmock.domains.interview.protocols.round_plan_schema import parse_round_plan
from realmock.platform.catalogs.company import get_company_context
from realmock.platform.database import api_db_session, sessions_db_session
from realmock.platform.services.candidate_read import (
    get_resume_agent_payload,
    get_user_profile,
)

logger = logging.getLogger(__name__)

#: Planner call budget for the round program (single small JSON object).
ROUND_PLAN_TIMEOUT_SECONDS = 40.0

ROUND_PLAN_STATUS_PENDING = ""
ROUND_PLAN_STATUS_READY = "ready"
ROUND_PLAN_STATUS_FAILED = "failed"


def _first_session(db: Any, process_id: int) -> InterviewSession | None:
    return (
        db.query(InterviewSession)
        .filter(InterviewSession.process_id == process_id)
        .order_by(InterviewSession.round_no.asc(), InterviewSession.id.asc())
        .first()
    )


async def generate_round_plan_for_process(process_id: int) -> None:
    """Background task: HR-plan the round program, persist on the process row.

    Never raises: any failure marks round_plan_status=failed so round
    creation degrades to the static chain immediately.
    """
    try:
        with sessions_db_session() as db:
            process = db.get(InterviewProcess, process_id)
            if process is None or getattr(process, "round_plan_status", "") == ROUND_PLAN_STATUS_READY:
                return
            first = _first_session(db, process_id)
            if first is None:
                process.round_plan_status = ROUND_PLAN_STATUS_FAILED
                db.commit()
                return
            llm = session_llm(db, first)
            if not llm.api_key:
                process.round_plan_status = ROUND_PLAN_STATUS_FAILED
                db.commit()
                return

            with api_db_session() as api_db:
                profile = get_user_profile(api_db, process.profile_id)
                resume_payload = get_resume_agent_payload(api_db, process.resume_id)

            # Custom (non-catalog) companies have no interview-style context:
            # research the company once here and persist the digest so later
            # rounds' flow planners and the interviewer prompt reuse it.
            digest = ""
            if needs_company_research(process.company or ""):
                digest = (
                    await research_company_context(
                        llm,
                        company=process.company or "",
                        role=process.role,
                        level=process.level,
                        ui_locale=process.ui_locale or None,
                    )
                    or ""
                )
                process.company_research = digest
                db.commit()

            user_msg = build_round_plan_user_message(
                role=process.role,
                level=process.level,
                company=process.company,
                round_budget=max(1, process.max_rounds or 1),
                profile=profile,
                resume_summary=resume_payload if isinstance(resume_payload, dict) else None,
                company_context=blend_company_context(
                    get_company_context(process.company or ""), digest
                ),
            )
            try:
                raw = await asyncio.wait_for(
                    llm.chat_json(
                        [
                            {"role": "system", "content": hr_planner_system_prompt()},
                            {"role": "user", "content": user_msg},
                        ],
                        temperature=0.3,
                    ),
                    timeout=ROUND_PLAN_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning("round plan generation timed out pid=%s", process_id)
                raw = None
            except Exception as e:
                logger.warning("round plan generation failed pid=%s: %s", process_id, e)
                raw = None

            plan = parse_round_plan(raw) if raw else None
            if plan is None:
                process.round_plan_status = ROUND_PLAN_STATUS_FAILED
                db.commit()
                return
            # Honor the user budget even if the model overshoots.
            plan.rounds = plan.rounds[: max(1, process.max_rounds or 1)]
            for i, r in enumerate(plan.rounds, start=1):
                r.round_no = i
            process.round_plan = json.dumps(plan.to_dict(), ensure_ascii=False)
            process.round_plan_status = ROUND_PLAN_STATUS_READY
            db.commit()
            logger.info(
                "round plan ready pid=%s rounds=%d", process_id, len(plan.rounds)
            )
    except Exception:
        logger.exception("generate_round_plan_for_process crashed pid=%s", process_id)
        try:
            with sessions_db_session() as db:
                process = db.get(InterviewProcess, process_id)
                if process is not None:
                    process.round_plan_status = ROUND_PLAN_STATUS_FAILED
                    db.commit()
        except Exception:
            logger.exception("round plan failure marking failed pid=%s", process_id)


__all__ = [
    "ROUND_PLAN_STATUS_FAILED",
    "ROUND_PLAN_STATUS_PENDING",
    "ROUND_PLAN_STATUS_READY",
    "ROUND_PLAN_TIMEOUT_SECONDS",
    "generate_round_plan_for_process",
]
