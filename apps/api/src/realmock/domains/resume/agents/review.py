"""Resume-review Agent: tool loop, JSON finalize, event callbacks.

Reusable GitHub / search / profile / resume tools live in platform.
The process/plan tool is resume-only and is composed here.
"""

from __future__ import annotations

import asyncio
import json
import logging
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
from realmock.domains.resume.schemas.limits import (
    REVIEW_AGENT_TEMPERATURE,
    REVIEW_KEEP_RECENT_MESSAGES,
    REVIEW_MAX_OUTPUT_TOKENS,
    REVIEW_MAX_PLAN_STEPS,
    REVIEW_MAX_ROUNDS,
    REVIEW_MAX_TOOLS_PER_ROUND,
    REVIEW_MIN_PLAN_STEPS,
    REVIEW_REPAIR_TIMEOUT_SECONDS,
    REVIEW_SEARCH_MAX_RESULTS,
    REVIEW_TOOL_TIMEOUT_SECONDS,
)
from realmock.domains.resume.services.analysis_prompt import (
    get_review_agent_prompt,
    review_json_schema_text,
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
)
from realmock.platform.capabilities.ai.context.blobs import compress_text_blob
from realmock.platform.capabilities.ai.context.manager import compact_with_summary, upsert_memory_block
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.capabilities.ai.llm.defaults import resolve_context_window, resolve_max_output_tokens
from realmock.platform.capabilities.ai.llm.json_extract import (
    extract_json_object as _extract_json_object,
    truncate_chunk,
)
from realmock.platform.core.errors import ApiBusinessError, raise_error
from realmock.platform.models import Resume
from realmock.platform.services.candidate_read import get_default_user_profile

logger = logging.getLogger(__name__)

# Event contract lives in platform (single source); aliases keep the
# established import path working for callers and tests.
ReviewEvent = AgentEvent
OnReviewEvent = OnAgentEvent

# Defense-in-depth caps: repair evidence joins already-compacted tool
# observations; these only bound the join itself.
_EVIDENCE_CHUNK_CHARS = 8_000
_EVIDENCE_TOTAL_CHARS = 40_000
# Circuit breaker: a tool failing this many times in a row is refused without
# spending another call, so one broken tool cannot eat the round budget.
_TOOL_CIRCUIT_BREAKER_STREAK = 3

_WRAP_UP_MESSAGE = {
    "role": "system",
    "content": (
        "This is the last tool-calling round. If evidence is sufficient, output the "
        "complete evaluation JSON now and do not call tools. If one critical fact is "
        "still missing, call only that tool."
    ),
}

# Bounded plan enforcement: the first user message already orders plan-first;
# from the second round on, pin a reminder on top until the model declares a
# plan. The tool-derived fallback still applies so progress never stalls.
_PLAN_REMINDER_MAX = 3


def _plan_reminder_text() -> str:
    """One-shot prompt builder for the next LLM round when no plan exists."""
    return (
        "Create the review plan now: call review_set_plan before any other tool. "
        f"Declare {REVIEW_MIN_PLAN_STEPS}-{REVIEW_MAX_PLAN_STEPS} steps in the resume's "
        "language; the last step must generate the evaluation JSON. "
        "Then keep the plan in sync with review_update_step as you work."
    )


def _needs_plan_reminder(*, has_plan: bool, round_index: int, reminders_used: int) -> bool:
    """Remind from the second round on, bounded so context never fills with nags."""
    return (not has_plan) and round_index >= 1 and reminders_used < _PLAN_REMINDER_MAX


# User-facing reasons when a PDF review runs without page images. The notice
# is explicit degradation, never a silent text-only fallback.
_VISUAL_UNAVAILABLE_REASONS: dict[str, tuple[str, str]] = {
    "no_vision": (
        "模型未启用图片输入，本次按纯文本评审；版式/字体结论仅供参考",
        "Vision input is disabled; text-only review — layout/typeface findings are approximate",
    ),
    "missing_file": (
        "原始 PDF 文件缺失，本次按纯文本评审",
        "Original PDF is missing; text-only review",
    ),
    "render_failed": (
        "PDF 页面渲染失败，本次按纯文本评审",
        "PDF page rendering failed; text-only review",
    ),
    "filtered": (
        "页面图超出模型上下文被过滤，本次按纯文本评审",
        "Page images were dropped by the context budget; text-only review",
    ),
}


def _vision_notice_message(*, locale: str, file_type: str, visual_status: str) -> str | None:
    """Notice text when a PDF review runs without page images; None otherwise."""
    if file_type.lower() != "pdf" or visual_status == "ok":
        return None
    reason = _VISUAL_UNAVAILABLE_REASONS.get(visual_status)
    if reason is None:
        return None
    zh_reason, en_reason = reason
    return en_reason if locale == "en" else zh_reason


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


# NOTE: _iter_balanced_objects / _extract_json_object live in
# platform.capabilities.ai.llm.json_extract (single source); the import
# aliases above keep the established import path working.


def _content_as_text(content: Any) -> str:
    """Flatten a chat content field; images become a short marker, not the data URL."""
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                parts.append(str(item))
                continue
            text = str(item.get("text") or "").strip()
            if text:
                parts.append(text)
            elif item.get("type") == "image_url" or item.get("image_url"):
                parts.append("[attached page image]")
        return "\n".join(parts)
    return str(content or "")


def _truncate_chunk(text: str, *, limit: int = _EVIDENCE_CHUNK_CHARS) -> str:
    """Cap one evidence chunk; platform helper with the resume-domain default."""
    return truncate_chunk(text, limit=limit)


def evidence_for_repair(messages: list[dict[str, Any]], draft: str) -> str:
    """Ground a JSON-repair pass in the resume overview and tool observations."""
    chunks: list[str] = []
    for message in messages:
        role = str(message.get("role") or "")
        if role == "user":
            text = _content_as_text(message.get("content")).strip()
            if text:
                chunks.append("RESUME_OVERVIEW:\n" + _truncate_chunk(text))
        elif role == "tool":
            text = _content_as_text(message.get("content")).strip()
            if text:
                name = str(message.get("name") or message.get("tool_call_id") or "tool")
                chunks.append(f"TOOL_{name}:\n{_truncate_chunk(text)}")
    draft_text = (draft or "").strip()
    if draft_text:
        chunks.append("DRAFT:\n" + _truncate_chunk(draft_text))
    joined = "\n\n".join(chunks)
    if len(joined) > _EVIDENCE_TOTAL_CHARS:
        keep = max(80, (_EVIDENCE_TOTAL_CHARS - 80) // 2)
        return (
            joined[:keep]
            + f"\n…[evidence truncated; original {len(joined)} chars]…\n"
            + joined[-keep:]
        )
    return joined


async def finalize_review_json(
    loop: LoopResult,
    llm: LLMClient,
    *,
    locale: str,
    max_output: int,
) -> dict[str, Any]:
    """Parse the loop's final JSON, or repair it from gathered evidence.

    Does not invent an evaluation from an empty prompt. Missing evidence → C0001.
    Repair failure → C0002.
    """
    payload = _extract_json_object(loop.final_content or "")
    if isinstance(payload, dict):
        return payload
    silent = not str(loop.final_content or "").strip() and not loop.tool_used
    if silent:
        raise_error("C0001")
    logger.info(
        "Resume review final content was not JSON (len=%s); requesting a grounded JSON repair pass",
        len(str(loop.final_content or "")),
    )
    evidence = evidence_for_repair(loop.messages, loop.final_content or "")
    if not evidence.strip():
        raise_error("C0001")
    repair_src = await compress_text_blob(
        llm,
        evidence,
        purpose="resume review JSON repair",
    )
    try:
        repaired = await asyncio.wait_for(
            llm.chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "Repair the following resume-review evidence into the evaluation "
                            "JSON schema below. Output a single JSON object that matches this "
                            "schema exactly — same keys, same shapes, every field present:\n"
                            f"{review_json_schema_text()}\n"
                            f"Write user-facing fields in {locale}. "
                            "Use only facts present in the evidence. Do not invent scores, repos, or quotes. "
                            "No tool calls."
                        ),
                    },
                    {"role": "user", "content": repair_src},
                ],
                temperature=0.2,
                max_tokens=min(max_output, REVIEW_MAX_OUTPUT_TOKENS),
            ),
            timeout=REVIEW_REPAIR_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning("Resume review JSON repair failed: %s", exc)
        raise_error("C0002", cause=exc)
    if not isinstance(repaired, dict):
        raise_error("C0002")
    return repaired


async def _invoke_review_tool(
    bundle: ToolBundle,
    name: str,
    args: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Run one tool. Platform helper with the resume-domain timeout.

    ApiBusinessError propagates through the Agent loop to the caller;
    only timeouts/unexpected exceptions become JSON observations.
    """
    return await invoke_with_timeout(
        bundle, name, args, timeout=REVIEW_TOOL_TIMEOUT_SECONDS, context=context
    )


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
) -> Callable[[str, dict[str, Any]], Awaitable[str]]:
    """Build the Agent-loop ``execute`` callback with SSE progress events.

    Kept as a factory (instead of inline closures) so ``run_resume_review``
    stays orchestration-only and the executor is independently testable.
    """
    tool_seq = 0
    error_streak: dict[str, int] = {}

    def _circuit_open_observation(tool: str) -> str:
        """Refuse a repeatedly failing tool without spending another call."""
        return json.dumps(
            {
                "error": "circuit_open",
                "tool": tool,
                "message": (
                    f"{tool} failed {_TOOL_CIRCUIT_BREAKER_STREAK} times in a row; "
                    "further calls are blocked to protect the tool budget. "
                    "Continue with other tools or the evidence already gathered."
                ),
            },
            ensure_ascii=False,
        )

    async def execute_tool_call(name: str, args: dict[str, Any]) -> str:
        nonlocal tool_seq
        used_tools.append(name)
        # Plan bookkeeping already arrives as ``plan`` events; do not emit tool_step.
        if name.startswith(PLAN_TOOL_PREFIX):
            raw, _status = await _invoke_review_tool(bundle, name, args, context)
            return raw
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
        if error_streak.get(name, 0) >= _TOOL_CIRCUIT_BREAKER_STREAK:
            raw, status = _circuit_open_observation(name), "error"
        else:
            raw, status = await _invoke_review_tool(bundle, name, args, context)
            if status == "error":
                error_streak[name] = error_streak.get(name, 0) + 1
            else:
                error_streak.pop(name, None)
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
    """Run the tool loop and return a raw analysis dict (not yet normalized)."""
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
    execute_tool_call = _build_tool_executor(bundle, used_tools, on_event, error_context)

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
        if _needs_plan_reminder(
            has_plan=bool(process.steps),
            round_index=round_index,
            reminders_used=plan_reminders,
        ):
            plan_reminders += 1
            return [{"role": "system", "content": _plan_reminder_text()}, *base]
        return base

    async def compact_observation(text: str) -> str:
        return await compress_text_blob(llm, text, purpose="resume review tool result")

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
            wrap_up_hint=_WRAP_UP_MESSAGE,
            prepare_messages=prepare_messages,
            compact_observation=compact_observation,
            error_context=error_context,
        )
    except ApiBusinessError:
        _restore_max_tokens(llm, original_max_tokens)
        raise
    except Exception as exc:
        logger.exception("Resume review agent loop failed")
        _restore_max_tokens(llm, original_max_tokens)
        raise_error("C0001", cause=exc)

    _restore_max_tokens(llm, original_max_tokens)

    if not process.steps:
        await process.set_plan(plan_titles_from_tool_names(used_tools))

    payload = await finalize_review_json(
        loop, llm, locale=locale, max_output=max_output
    )

    return _attach_review_audit(payload, search_queries, process)


__all__ = [
    "build_resume_snapshot",
    "build_review_bundle",
    "evidence_for_repair",
    "finalize_review_json",
    "run_resume_review",
]
