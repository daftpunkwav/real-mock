"""Detailed reference answer: a copy-ready model reply for the candidate.

The full candidate grounding (profile / resume / company) is injected
verbatim, so the default path is a single zero-tool writer call; a short
GitHub tool loop runs only when the question or background signals an
external repository to verify, and the loop's own closing answer is reused
(the writer pass remains only as a fallback). Never raises: any failure
yields None so the caller can degrade to the fast outline.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.interview.agents.agent_policies import HINT_LOOP
from realmock.domains.interview.agents.agent_text import strip_markers, strip_think_blocks
from realmock.domains.interview.agents.tools import execute_interview_tool
from realmock.domains.interview.agents.tool_guard import ToolGuard
from realmock.platform.capabilities.ai.agent import run_agent_loop
from realmock.platform.capabilities.ai.agent.tools import (
    github_tool_specs,
    openai_tool,
)
from realmock.platform.catalogs.company import get_company_context
from realmock.platform.database import api_db_session
from realmock.platform.services.candidate_read import (
    get_default_user_profile,
    get_resume_agent_payload,
    get_user_profile,
)
from realmock.domains.interview.agents.hint.hint_prompts import (
    HINT_MODEL_ANSWER_WRITER_SYSTEM,
    HINT_TOOL_FREE_WRAP_UP,
    hint_coach_system,
)

logger = logging.getLogger(__name__)

#: Whole-generation wall-clock budget (tool loop + final synthesis). The room
#: client waits up to ~90s in detailed mode; the remainder is safety margin.
FULL_HINT_BUDGET_SECONDS = HINT_LOOP.budget_seconds
#: Tool rounds for evidence gathering (bounded: this is assistance, not a turn).
FULL_HINT_MAX_ROUNDS = HINT_LOOP.max_rounds

#: The full hint's grounding (resume/profile/company) is injected verbatim, so
#: tools are only worth their latency when the question points at external
#: evidence — a GitHub repository to verify.
_REPO_SIGNAL_RE = re.compile(
    r"\bgithub[\w-]*\b|\brepos?\b|\bcommits?\b|\bstars?\b|开源项目|代码仓库", re.IGNORECASE
)


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
        logger.warning("full reference hint timed out sid=%s", getattr(session, "id", None))
        return None
    except Exception:
        logger.warning(
            "full reference hint failed sid=%s", getattr(session, "id", None), exc_info=True
        )
        return None


def _render_profile(profile: Any) -> str:
    """Full candidate profile block (readable lines; no truncation)."""
    if profile is None:
        return ""
    fields = [
        ("Name", getattr(profile, "name", "")),
        ("Target role", getattr(profile, "target_role", "")),
        ("Job direction", getattr(profile, "job_direction", "")),
        (
            "School / major",
            f"{getattr(profile, 'school', '') or ''} {getattr(profile, 'major', '') or ''}".strip(),
        ),
        ("Education level", getattr(profile, "education_level", "")),
        (
            "Experience",
            f"{getattr(profile, 'experience_years', '')} years {getattr(profile, 'work_years_detail', '') or ''}".strip(),
        ),
        ("Current company", getattr(profile, "current_company", "")),
        ("Tech domains", ", ".join(getattr(profile, "tech_domains_list", None) or [])),
        ("Certificates", getattr(profile, "certificates", "")),
        ("English level", getattr(profile, "english_level", "")),
        ("Signature projects", getattr(profile, "signature_projects", "")),
        ("Strengths", getattr(profile, "strengths", "")),
        ("Weaknesses", getattr(profile, "weaknesses", "")),
        ("Career highlights", getattr(profile, "career_highlights", "")),
        ("Self introduction", getattr(profile, "self_intro", "")),
        ("GitHub", getattr(profile, "github_username", "")),
    ]
    lines = ["## Candidate profile"]
    for label, value in fields:
        text = str(value or "").strip()
        if text:
            lines.append(f"{label}: {text}")
    return "\n".join(lines)


def _render_resume(payload: dict[str, Any] | None) -> str:
    """Full parsed-resume block (list entries rendered readable, untruncated)."""
    if not isinstance(payload, dict):
        return ""
    parsed = payload.get("parsed") if isinstance(payload.get("parsed"), dict) else {}
    if not parsed:
        return ""
    lines = ["## Parsed resume"]
    for key, value in parsed.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            lines.append(f"{key}:")
            for i, item in enumerate(value, start=1):
                entry = "; ".join(
                    f"{k}: {str(v).strip()}" for k, v in item.items() if str(v or "").strip()
                )
                if entry:
                    lines.append(f"  {i}. {entry}")
        elif isinstance(value, list):
            lines.append(f"{key}: {', '.join(str(v) for v in value)}")
        else:
            text = str(value or "").strip()
            if text:
                lines.append(f"{key}: {text}")
    return "\n".join(lines)


async def _load_grounding(session: Any) -> str:
    """Company + full candidate grounding (no truncation; 1M-window policy)."""
    sections: list[str] = []
    company_ctx = get_company_context(getattr(session, "company", "") or "")
    if company_ctx:
        sections.append(f"## Company context\n{company_ctx}")
    try:
        with api_db_session() as api_db:
            profile_id = getattr(session, "profile_id", None)
            resume_id = getattr(session, "resume_id", None)
            profile = (
                get_user_profile(api_db, profile_id)
                if profile_id
                else get_default_user_profile(api_db)
            )
            payload = get_resume_agent_payload(api_db, resume_id) if resume_id else None
    except Exception:
        logger.debug("hint grounding load failed", exc_info=True)
        return ""
    profile_block = _render_profile(profile)
    if profile_block:
        sections.append(profile_block)
    resume_block = _render_resume(payload)
    if resume_block:
        sections.append(resume_block)
    return "\n\n".join(sections)


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
    grounding = await _load_grounding(session)
    user_content = (
        (f"{grounding}\n\n" if grounding else "")
        + (f"Candidate background summary:\n{background}\n\n" if background else "")
        + f"Interviewer question: {question}\n\n"
    )

    # Zero-tool fast path: the grounding above already carries the full
    # resume/profile/company material, so only an explicit repository signal
    # justifies paying for a tool loop (github verification only).
    if not _REPO_SIGNAL_RE.search(question or "") and not _REPO_SIGNAL_RE.search(background or ""):
        return await _write_direct_answer(llm, lang_name, user_content)
    return await _run_github_tool_loop(llm, db, session, agent_state, user_content, lang_name)


async def _write_direct_answer(llm: Any, lang_name: str, user_content: str) -> str | None:
    """Single grounding-only writer call (no tools); None when empty."""
    writer_messages = [
        {
            "role": "system",
            "content": HINT_MODEL_ANSWER_WRITER_SYSTEM.format(lang_name=lang_name),
        },
        {
            "role": "user",
            "content": user_content
            + "Write the final model answer now (first person, copy-ready):",
        },
    ]
    text = await llm.chat(writer_messages, temperature=0.4, max_tokens=1500)
    return strip_markers(strip_think_blocks(text or "")).strip() or None


async def _run_github_tool_loop(
    llm: Any,
    db: Session,
    session: Any,
    agent_state: dict[str, Any],
    user_content: str,
    lang_name: str,
) -> str | None:
    """Verify the referenced repository with tools, then answer.

    The loop's own closing content already IS the evidence-grounded answer —
    reuse it instead of a second synthesis call (the full hint is on the
    room's critical path; this roughly halves its latency). The writer pass
    only runs as a fallback when the loop ended on tool calls with no text.
    """
    tools = [openai_tool(spec) for spec in github_tool_specs()]
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
            "content": user_content
            + "Verify the referenced repository with tools, then give the model answer:",
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
        trace.append(
            {"tool": f"hint:{name}", "ok": not str(result).startswith("Tool execution failed")}
        )
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
        # Protocol-level final answer instead of an ignorable advisory hint.
        final_round_tool_free=FULL_HINT_MAX_ROUNDS >= 2,
        wrap_up_hint=HINT_TOOL_FREE_WRAP_UP,
        error_context={"domain": "interview", "session": getattr(session, "id", None)},
    )
    if loop.final_content and loop.final_content.strip():
        cleaned = strip_markers(strip_think_blocks(loop.final_content)).strip()
        if cleaned:
            return cleaned

    writer_messages = [
        {"role": "system", "content": HINT_MODEL_ANSWER_WRITER_SYSTEM.format(lang_name=lang_name)},
        *_writer_view(loop.messages),
        {
            "role": "user",
            "content": "Write the final model answer now (first person, copy-ready):",
        },
    ]
    text = await llm.chat(writer_messages, temperature=0.4, max_tokens=1500)
    cleaned = strip_markers(strip_think_blocks(text or "")).strip()
    return cleaned or None


def _writer_view(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Loop history shaped for a plain ``llm.chat`` call (no tools parameter).

    Assistant ``tool_calls`` / ``thinking_blocks`` fields are stripped and the
    tool observations are folded into a user message: strict OpenAI-compatible
    gateways reject tool fields (or orphan tool results) on a request that
    declares no tools, and the folded evidence is exactly what the writer needs.
    """
    names: dict[str, str] = {}
    for m in messages:
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function") or {}
            if tc.get("id") and fn.get("name"):
                names[str(tc["id"])] = str(fn["name"])

    view: list[dict[str, Any]] = []
    evidence: list[str] = []
    for m in messages:
        role = m.get("role")
        if role == "tool":
            content = str(m.get("content") or "")
            if content:
                name = names.get(str(m.get("tool_call_id") or ""), "tool")
                evidence.append(f"[{name}] {content}")
            continue
        if role == "assistant":
            cleaned = {k: v for k, v in m.items() if k not in ("tool_calls", "thinking_blocks")}
            if not m.get("tool_calls") or cleaned.get("content"):
                view.append(cleaned)
            continue
        if role in ("user", "system"):
            view.append(m)
    if evidence:
        view.append(
            {
                "role": "user",
                "content": "Tool results gathered so far:\n" + "\n\n".join(evidence),
            }
        )
    return view


__all__ = ["FULL_HINT_BUDGET_SECONDS", "FULL_HINT_MAX_ROUNDS", "generate_full_reference_hint"]
