"""Resume-review Agent: tool loop, JSON finalize, event callbacks.

Reusable GitHub / search / profile / resume tools live in platform.
The process/plan tool is resume-only and is composed here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.resume.agents.observe import (
    public_tool_args,
    search_hosts_from_observation,
)
from realmock.domains.resume.agents.payload import build_review_user_message
from realmock.domains.resume.agents.process import (
    PLAN_TOOL_PREFIX,
    ReviewProcess,
    plan_titles_from_tool_names,
    process_tool_specs,
)
# The JSON finalize chain and review copy blocks live in sibling modules
# (review_json.py / review_prompts.py); these imports keep the established
# ``review`` import path working for callers and tests.
from realmock.domains.resume.agents.review_json import (
    _content_as_text,  # noqa: F401  # compatibility re-export (tests)
    _request_forced_final_answer,
    evidence_for_repair,
    finalize_review_json,
)
from realmock.domains.resume.agents.review_prompts import (
    _budget_refusal_text,
    _circuit_refusal_text,
    _emit_finalize_notice,
    _vision_notice_message,
)
from realmock.domains.resume.schemas.limits import (
    REVIEW_AGENT_TEMPERATURE,
    REVIEW_COUNTDOWN_ROUNDS,
    REVIEW_FORCED_FINAL_TIMEOUT_SECONDS,
    REVIEW_KEEP_RECENT_MESSAGES,
    REVIEW_MAX_OUTPUT_TOKENS,
    REVIEW_MAX_ROUNDS,
    REVIEW_MAX_TOOLS_PER_ROUND,
    REVIEW_MAX_TOTAL_TOOL_CALLS,
    REVIEW_OBSERVATION_MAX_CHARS,
    REVIEW_SEARCH_MAX_RESULTS,
)
from realmock.domains.resume.prompts import (
    REVIEW_PLAN_COMPLETE_MESSAGE,
    REVIEW_WRAP_UP_TOOL_FREE_MESSAGE,
    get_review_agent_prompt,
    review_plan_reminder_text,
)
from realmock.domains.resume.services.review_context import (
    build_review_calibration as _calibration_for_review,
)
from realmock.domains.resume.services.sites import RESUME_MARKET_SEARCH_SITES
from realmock.platform.capabilities.ai.agent import (
    AgentEvent,
    LoopResult,
    OnAgentEvent,
    WorkingMemory,
    emit_agent_event,
    run_agent_loop,
)
from realmock.platform.capabilities.ai.agent.tools import (
    ResumeSnapshot,
    ToolBundle,
    github_tool_specs,
    invoke_with_timeout,
    profile_from_orm,
    profile_tool_specs,
    resume_tool_specs,
    search_tool_spec,
    snapshot_from_payload,
    web_fetch_tool_spec,

    ToolRunGuard,)
from realmock.platform.capabilities.ai.context.manager import compact_with_summary, upsert_memory_block
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.capabilities.ai.llm.defaults import resolve_context_window, resolve_max_output_tokens
from realmock.platform.capabilities.ai.llm.json_extract import (
    # Imported under its established private alias so tests can keep
    # importing it from ``review``; the finalize chain uses review_json.py.
    extract_json_object as _extract_json_object,  # noqa: F401
)
from realmock.platform.core.errors import ApiBusinessError, raise_error
from realmock.platform.models import Resume
from realmock.platform.services.candidate_read import get_default_user_profile

logger = logging.getLogger(__name__)

# Event contract lives in platform (single source); aliases keep the
# established import path working for callers and tests.
ReviewEvent = AgentEvent
OnReviewEvent = OnAgentEvent

# Circuit breaker: the exact same call (tool + arguments) failing this many
# times in a row is refused without spending another call. Different arguments
# are never blocked — the workload differs, so the model decides.
_TOOL_CIRCUIT_BREAKER_STREAK = 3

# Bounded plan enforcement: the first user message already orders plan-first;
# from the second round on, append a transient reminder at the tail until the
# model declares a plan (tail position keeps the stable prefix cacheable). The
# tool-derived fallback still applies so progress never stalls.
_PLAN_REMINDER_MAX = 3


async def _truncate_observation(text: str) -> str:
    """Deterministic head+tail cap for one tool observation.

    Attention bound, not a context-space bound: raw evidence stays readable at
    both ends (model-written args and the tool's summary/marker live there),
    only the middle is elided behind an explicit marker.
    """
    body = str(text or "")
    limit = REVIEW_OBSERVATION_MAX_CHARS
    if len(body) <= limit:
        return body
    head = limit * 70 // 100
    tail = limit - head
    return body[:head] + "\n…[middle truncated]…\n" + body[-tail:]


# Page-image retirement: the 8 rendered pages are re-sent with EVERY round and
# dominate per-request latency on slow models. Once the layout review step has
# concluded, its findings live in the step notes and the images stop earning
# their cost — later rounds continue text-only. If no step clearly owns the
# layout review, retire the images after a bounded share of rounds anyway.
_LAYOUT_STEP_RE = re.compile(
    r"版面|版式|排版|页面图|图像|layout|visual|image|typograph", re.I
)
_IMAGE_RETIRE_ROUND_RATIO = 2 / 3
_IMAGE_RETIRE_MIN_ROUND = 8
_RETIRED_IMAGE_MARKER = (
    "[Original page images were attached earlier; the layout review is complete "
    "and its findings are recorded in your step notes.]"
)


def _layout_review_concluded(process: Any) -> bool:
    """True when a plan step owning the layout review has finished."""
    for step in getattr(process, "steps", []) or []:
        if step.status in ("done", "skipped") and _LAYOUT_STEP_RE.search(step.title or ""):
            return True
    return False


def _retire_page_images(message: dict[str, Any]) -> dict[str, Any]:
    """Replace attached page images with an explicit text marker (new dict)."""
    content = message.get("content")
    if not isinstance(content, list):
        return message
    if not any(
        isinstance(item, dict) and item.get("type") == "image_url" for item in content
    ):
        return message
    replaced: list[dict[str, Any]] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "image_url":
            replaced.append({"type": "text", "text": _RETIRED_IMAGE_MARKER})
        else:
            replaced.append(item)
    return {**message, "content": replaced}


def _needs_plan_reminder(*, has_plan: bool, round_index: int, reminders_used: int) -> bool:
    """Remind from the second round on, bounded so context never fills with nags."""
    return (not has_plan) and round_index >= 1 and reminders_used < _PLAN_REMINDER_MAX


# NOTE: _calibration_for_review is imported from services.review_context above
# (single source); the alias keeps the established import path working.


def _parsed_dict(resume: Resume) -> dict[str, Any]:
    try:
        data = json.loads(resume.parsed_profile or "{}")
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _query_from_args(name: str, args: dict[str, Any]) -> str:
    for key in ("query", "section", "id", "repo", "path", "username", "status"):
        value = args.get(key)
        if value:
            return str(value)[:120]
    return name


async def _invoke_review_tool(
    bundle: ToolBundle,
    name: str,
    args: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Run one tool. Platform helper; the timeout comes from the tool's own
    ``timeout_seconds`` declaration, falling back to the platform default.

    ApiBusinessError propagates through the Agent loop to the caller;
    only timeouts/unexpected exceptions become JSON observations.
    """
    return await invoke_with_timeout(bundle, name, args, context=context)


async def _emit(on_event: OnReviewEvent | None, event: ReviewEvent) -> None:
    """Deliver one SSE progress event; platform helper (failures only logged)."""
    await emit_agent_event(on_event, event)


def _reinsert_first_user(
    original: list[dict[str, Any]],
    compacted: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep the first user message (overview / page images) after compaction."""
    first_user = next((m for m in original if m.get("role") == "user"), None)
    if first_user is None:
        return compacted
    if any(m is first_user for m in compacted):
        return compacted
    idx = 0
    while idx < len(compacted) and compacted[idx].get("role") == "system":
        idx += 1
    return compacted[:idx] + [first_user] + compacted[idx:]


def build_resume_snapshot(resume: Resume, *, has_visual_pages: bool = False) -> ResumeSnapshot:
    """Snapshot for resume_* tools. Layout notes come from parsed JSON when present."""
    parsed = _parsed_dict(resume)
    return snapshot_from_payload(
        {
            "resume_id": int(resume.id or 0),
            "filename": resume.filename or "",
            "file_type": resume.file_type or "",
            "raw_text": resume.raw_text or "",
            "parsed": parsed,
            "layout_notes": str(parsed.get("layout_notes") or ""),
        },
        has_visual_pages=has_visual_pages,
    )


def build_review_bundle(
    *,
    snapshot: ResumeSnapshot,
    db: Session,
    process: ReviewProcess,
    search_queries: list[str],
) -> ToolBundle:
    """Compose shared tools + resume-only process tools. No FastAPI."""
    bundle = ToolBundle()
    bundle.extend(process_tool_specs(process))
    bundle.extend(resume_tool_specs(snapshot))
    bundle.extend(profile_tool_specs(profile_from_orm(get_default_user_profile(db))))
    bundle.extend(github_tool_specs())

    def _on_hits(query: str, _hits: list) -> None:
        if query and query not in search_queries:
            search_queries.append(query)

    bundle.add(
        search_tool_spec(
            default_max_results=REVIEW_SEARCH_MAX_RESULTS,
            sites=list(RESUME_MARKET_SEARCH_SITES) or None,
            on_hits=_on_hits,
            force_job_boards=True,
        )
    )
    bundle.add(web_fetch_tool_spec())
    return bundle


def _restore_max_tokens(llm: LLMClient, value: Any) -> None:
    """Best-effort restore of a mutated client budget; never mask the real error."""
    try:
        llm.max_tokens = value
    except Exception:
        pass


def _merge_search_queries_used(existing: Any, tracked: list[str]) -> list[str]:
    """Merge model-emitted queries with tool-observed ones, preserving order."""
    merged = [str(q) for q in existing] if isinstance(existing, list) and existing else list(tracked)
    for query in tracked:
        if query not in merged:
            merged.append(query)
    return merged


def _attach_review_audit(
    payload: dict[str, Any],
    search_queries: list[str],
    process: ReviewProcess,
) -> dict[str, Any]:
    """Attach observability fields without changing evaluation content."""
    payload["search_queries_used"] = _merge_search_queries_used(
        payload.get("search_queries_used"), search_queries
    )
    payload["_agent_steps"] = process.snapshot()
    return payload


def _build_tool_executor(
    bundle: ToolBundle,
    used_tools: list[str],
    on_event: OnReviewEvent | None,
    context: dict[str, Any] | None = None,
    guard: ToolRunGuard | None = None,
    activity_sink: Callable[[str], None] | None = None,
) -> Callable[[str, dict[str, Any]], Awaitable[str]]:
    """Build the Agent-loop ``execute`` callback with SSE progress events.

    ``guard`` (shared :class:`ToolRunGuard` policy) counts non-plan calls that
    pass the budget gate so the per-round progress line and the total-call
    refusal share one number; circuit-breaker refusals refund their slot.
    ``activity_sink`` receives one compact label per executed non-plan call and
    feeds the deterministic step-note fallback in ``ReviewProcess``.
    Kept as a factory (instead of inline closures) so ``run_resume_review``
    stays orchestration-only and the executor is independently testable.
    """
    tool_seq = 0
    if guard is None:
        guard = ToolRunGuard(
            max_total_calls=REVIEW_MAX_TOTAL_TOOL_CALLS,
            circuit_streak=_TOOL_CIRCUIT_BREAKER_STREAK,
            budget_refusal=_budget_refusal_text,
            circuit_refusal=_circuit_refusal_text,
        )

    async def execute_tool_call(name: str, args: dict[str, Any]) -> str:
        nonlocal tool_seq
        used_tools.append(name)
        # Plan bookkeeping already arrives as ``plan`` events; do not emit tool_step.
        if name.startswith(PLAN_TOOL_PREFIX):
            raw, _status = await _invoke_review_tool(bundle, name, args, context)
            return raw
        refusal = guard.acquire(name, args)
        if refusal is not None:
            return refusal
        tool_seq += 1
        step_id = f"tool-{tool_seq}"
        query = _query_from_args(name, args)
        public_args = public_tool_args(args)
        await _emit(
            on_event,
            {
                "type": "tool_step",
                "id": step_id,
                "name": name,
                "query": query,
                "status": "running",
                "args": public_args,
            },
        )
        raw, status = await _invoke_review_tool(bundle, name, args, context)
        guard.report(name, args, failed=(status == "error"))
        if activity_sink is not None:
            activity_sink(f"{name}({_query_from_args(name, args)})")
        await _emit(
            on_event,
            {
                "type": "tool_step",
                "id": step_id,
                "name": name,
                "query": query,
                "status": status,
                "args": public_args,
                "result": raw,
                "sites": search_hosts_from_observation(name, raw),
            },
        )
        return raw

    return execute_tool_call


async def run_resume_review(
    resume: Resume,
    db: Session,
    llm: LLMClient,
    *,
    locale: str,
    on_event: OnReviewEvent | None = None,
) -> dict[str, Any]:
    """Run the tool loop and return a raw analysis dict (not yet normalized).

    No wall-clock budget: rounds are paced by the per-round progress line, the
    countdown ladder, and a tool-free final round — the model is steered to the
    answer, never cut off mid-thought.
    """
    context_window = resolve_context_window(getattr(llm, "context_window", 0))
    max_output = resolve_max_output_tokens(getattr(llm, "max_tokens", 0))
    # Bound every round: a huge advertised ceiling lets reasoning models ramble
    # for tens of thousands of chars instead of emitting the final JSON.
    # Save and restore: the client object may be shared/reused by the caller.
    original_max_tokens = getattr(llm, "max_tokens", 0)
    llm.max_tokens = min(getattr(llm, "max_tokens", 0) or max_output, REVIEW_MAX_OUTPUT_TOKENS)

    snapshot = build_resume_snapshot(resume)
    user_message = await build_review_user_message(
        resume,
        snapshot,
        supports_vision=bool(getattr(llm, "supports_vision", False)),
        context_window=context_window,
        calibration=_calibration_for_review(resume, db),
    )
    visual_notice = _vision_notice_message(
        locale=locale,
        file_type=snapshot.file_type,
        visual_status=snapshot.visual_status,
    )
    if visual_notice is not None:
        await _emit(
            on_event,
            {"type": "notice", "kind": "vision_unavailable", "message": visual_notice},
        )
    search_queries: list[str] = []
    used_tools: list[str] = []
    memory = WorkingMemory()
    process = ReviewProcess()

    async def on_plan_change(steps: list[dict[str, Any]]) -> None:
        await _emit(on_event, {"type": "plan", "steps": steps})

    process.on_change = on_plan_change
    bundle = build_review_bundle(
        snapshot=snapshot, db=db, process=process, search_queries=search_queries
    )
    error_context = {"domain": "resume", "session": str(getattr(resume, "id", "") or "")}
    tool_guard = ToolRunGuard(
        max_total_calls=REVIEW_MAX_TOTAL_TOOL_CALLS,
        circuit_streak=_TOOL_CIRCUIT_BREAKER_STREAK,
        budget_refusal=_budget_refusal_text,
        circuit_refusal=_circuit_refusal_text,
    )
    execute_tool_call = _build_tool_executor(
        bundle,
        used_tools,
        on_event,
        error_context,
        guard=tool_guard,
        activity_sink=process.record_activity,
    )

    llm_round_index = 0
    plan_reminders = 0

    async def prepare_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nonlocal llm_round_index, plan_reminders
        round_index = llm_round_index
        llm_round_index += 1
        try:
            compacted = await compact_with_summary(
                messages,
                context_window,
                memory=memory,
                llm=llm,
                keep_recent=REVIEW_KEEP_RECENT_MESSAGES,
            )
        except Exception as exc:
            logger.warning("Resume review compaction failed, using uncompacted messages: %s", exc)
            base = list(messages)
        else:
            base = upsert_memory_block(_reinsert_first_user(messages, compacted), memory)
        # Retire page images once the layout review has concluded (or after a
        # bounded share of rounds): the findings live in the step notes, and
        # re-sending 8 images per round dominates latency on slow models.
        images_retired = _layout_review_concluded(process) or (
            round_index + 1
            >= max(
                _IMAGE_RETIRE_MIN_ROUND,
                int(REVIEW_MAX_ROUNDS * _IMAGE_RETIRE_ROUND_RATIO),
            )
        )
        if images_retired:
            base = [
                _retire_page_images(m) if m.get("role") == "user" else m for m in base
            ]
        # Transient suffix only: appending at the end keeps the stable prefix
        # (system / overview / working history) byte-identical for provider
        # prefix caches, and the end position carries the most attention.
        suffix: list[dict[str, Any]] = []
        if _needs_plan_reminder(
            has_plan=bool(process.steps),
            round_index=round_index,
            reminders_used=plan_reminders,
        ):
            plan_reminders += 1
            suffix.append({"role": "system", "content": review_plan_reminder_text()})
        if process.steps and all(
            step.status in ("done", "skipped") for step in process.steps
        ):
            # The plan is finished but the model is still calling tools: pin a
            # strong finalize instruction until it produces the answer.
            suffix.append(REVIEW_PLAN_COMPLETE_MESSAGE)
        # Budget awareness is NOT appended here: the platform loop injects its
        # own transient budget hint every round (loop.budget_hint), and a
        # second overlapping line would spend the strongest attention slot
        # twice on the same information.
        return [*base, *suffix]

    async def on_thinking(text: str) -> None:
        await _emit(on_event, {"type": "thinking", "content": text})

    messages = [
        {"role": "system", "content": get_review_agent_prompt(locale)},
        user_message,
    ]
    try:
        loop = await run_agent_loop(
            llm,
            messages,
            tools=bundle.definitions(),
            execute=execute_tool_call,
            max_rounds=REVIEW_MAX_ROUNDS,
            max_tools_per_round=REVIEW_MAX_TOOLS_PER_ROUND,
            temperature=REVIEW_AGENT_TEMPERATURE,
            on_thinking=on_thinking,
            drift_retry=True,
            wrap_up_hint=REVIEW_WRAP_UP_TOOL_FREE_MESSAGE,
            prepare_messages=prepare_messages,
            compact_observation=_truncate_observation,
            error_context=error_context,
            countdown_rounds=REVIEW_COUNTDOWN_ROUNDS,
            round_retries=1,
            final_round_tool_free=True,
        )
    except ApiBusinessError:
        _restore_max_tokens(llm, original_max_tokens)
        raise
    except Exception as exc:
        logger.exception("Resume review agent loop failed")
        _restore_max_tokens(llm, original_max_tokens)
        raise_error("C0001", cause=exc)

    # The loop ends with tools used but no final content when a round LLM call
    # failed (after retry) or the model returned an empty reply. Answer that
    # with one tool-free call over the gathered evidence, hard-bounded so a
    # hung request still leaves time for the lighter repair pass before the
    # frontend budget ends the run.
    if not (loop.final_content or "").strip() and loop.tool_used:
        await _emit_finalize_notice(on_event, locale, "forced_final")
        try:
            forced = await asyncio.wait_for(
                _request_forced_final_answer(llm, loop, locale=locale),
                timeout=REVIEW_FORCED_FINAL_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning("Resume review forced final answer did not finish: %s", exc)
            forced = None
        if forced is not None:
            loop = LoopResult(
                messages=loop.messages,
                final_content=forced,
                tool_used=True,
                halted=loop.halted,
                thinking=loop.thinking,
            )

    _restore_max_tokens(llm, original_max_tokens)

    if not process.steps:
        await process.set_plan(plan_titles_from_tool_names(used_tools))

    payload = await finalize_review_json(
        loop, llm, locale=locale, max_output=max_output, on_event=on_event
    )

    return _attach_review_audit(payload, search_queries, process)


__all__ = [
    "build_resume_snapshot",
    "build_review_bundle",
    "evidence_for_repair",
    "finalize_review_json",
    "run_resume_review",
]
