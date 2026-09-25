"""Detailed reference answer: tool-grounded model reply for the candidate.

Rounds cluster (see :mod:`realmock.domains.interview.agents`): the "full"
reference mode runs a short agent loop (profile / resume / GitHub tools) and
then synthesizes a first-person model answer the candidate can copy, adapt,
and send. Never raises: any failure yields None so the caller can degrade to
the fast outline.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.interview.agents.agent_text import strip_markers, strip_think_blocks
from realmock.domains.interview.agents.tools import (
    execute_interview_tool,
    get_interview_tool_definitions,
)
from realmock.domains.interview.agents.tool_guard import ToolGuard
from realmock.platform.capabilities.ai.agent import run_agent_loop
from realmock.domains.interview.agents.hint.hint_prompts import HINT_MODEL_ANSWER_WRITER_SYSTEM, hint_coach_system

logger = logging.getLogger(__name__)

#: Whole-generation wall-clock budget (tool loop + final synthesis). The room
#: client waits up to ~90s in detailed mode; the remainder is safety margin.
FULL_HINT_BUDGET_SECONDS = 60.0
#: Tool rounds for evidence gathering (bounded: this is assistance, not a turn).
FULL_HINT_MAX_ROUNDS = 2

async def generate_full_reference_hint(
    *,
    llm: Any,
    db: Session,
    session: Any,
    agent_state: dict[str, Any],
    question: str,
    background: str,
    flow_language: str = "zh",
    budget_seconds: float = FULL_HINT_BUDGET_SECONDS,
) -> str | None:
    """Gather evidence with tools, then write a copy-ready model answer.

    Args:
        llm: chat-capable client.
        db: short-lived sessions-DB session (owned by the caller).
        session: attached InterviewSession row (ids/company for tools).
        agent_state: mutable in-memory state (tool findings accumulate here).
        question: the interviewer's question (already extracted).
        background: candidate background summary for grounding.
        flow_language: "en" writes the answer in English, else Chinese.

    Returns:
        The model answer text, or None when anything failed (caller degrades).
    """
    try:
        return await asyncio.wait_for(
            _generate(llm, db, session, agent_state, question, background, flow_language),
            timeout=budget_seconds,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "full reference hint timed out sid=%s", getattr(session, "id", None)
        )
        return None
    except Exception:
        logger.warning(
            "full reference hint failed sid=%s", getattr(session, "id", None), exc_info=True
        )
        return None


async def _generate(
    llm: Any,
    db: Session,
    session: Any,
    agent_state: dict[str, Any],
    question: str,
    background: str,
    flow_language: str,
) -> str | None:
    lang_name = "English" if (flow_language or "").strip().lower().startswith("en") else "Chinese"
    tools = get_interview_tool_definitions(include_past_records=False)
    if not tools:
        return None
    guard = ToolGuard(
        state_fn=lambda: agent_state,
        error_context={"domain": "interview", "session": getattr(session, "id", None)},
    )

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": hint_coach_system(lang_name),
        },
        {
            "role": "user",
            "content": (
                f"Candidate background summary:\n{background or '(no detailed profile yet)'}\n\n"
                f"Interviewer question: {question}\n\n"
                "Verify key facts with tools, then give the model answer:"
            ),
        },
    ]

    async def execute(name: str, args: dict[str, Any]) -> str:
        return await guard.run(
            name,
            args,
            lambda: execute_interview_tool(
                name,
                args,
                db=db,
                resume_id=getattr(session, "resume_id", None),
                profile_id=getattr(session, "profile_id", None),
                agent_state=agent_state,
                llm=llm,
                session=session,
            ),
        )

    def _note_tool(name: str, args: dict[str, Any], result: str) -> None:
        trace = agent_state.setdefault("tool_trace", [])
        trace.append({"tool": f"hint:{name}", "ok": not str(result).startswith("Tool execution failed")})
        if len(trace) > 40:
            del trace[:-40]

    async def on_tool(name: str, args: dict[str, Any], result: str, tc_id: str) -> None:
        del tc_id
        _note_tool(name, args, result)

    loop = await run_agent_loop(
        llm,
        messages,
        tools=tools,
        execute=execute,
        max_rounds=FULL_HINT_MAX_ROUNDS,
        temperature=0.4,
        on_tool=on_tool,
    )
    # The loop's own closing content already IS the evidence-grounded answer —
    # reuse it instead of a second synthesis call (the full hint is on the
    # room's critical path; this roughly halves its latency). The writer pass
    # only runs as a fallback when the loop ended on tool calls with no text.
    if loop.final_content and loop.final_content.strip():
        cleaned = strip_markers(strip_think_blocks(loop.final_content)).strip()
        if cleaned:
            return cleaned

    writer_messages = [
        {"role": "system", "content": HINT_MODEL_ANSWER_WRITER_SYSTEM.format(lang_name=lang_name)},
        *[
            m for m in loop.messages
            if m.get("role") in ("user", "assistant", "tool", "system")
        ],
        {
            "role": "user",
            "content": "Write the final model answer now (first person, copy-ready):",
        },
    ]
    text = await llm.chat(writer_messages, temperature=0.4, max_tokens=800)
    cleaned = strip_markers(strip_think_blocks(text or "")).strip()
    return cleaned or None


__all__ = ["FULL_HINT_BUDGET_SECONDS", "FULL_HINT_MAX_ROUNDS", "generate_full_reference_hint"]
