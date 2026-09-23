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
from realmock.domains.resume.schemas.limits import (
    REVIEW_AGENT_TEMPERATURE,
    REVIEW_COUNTDOWN_ROUNDS,
    REVIEW_FORCED_FINAL_TIMEOUT_SECONDS,
    REVIEW_KEEP_RECENT_MESSAGES,
    REVIEW_MAX_OUTPUT_TOKENS,
    REVIEW_MAX_PLAN_STEPS,
    REVIEW_MAX_ROUNDS,
    REVIEW_MAX_TOOLS_PER_ROUND,
    REVIEW_MAX_TOTAL_TOOL_CALLS,
    REVIEW_MIN_PLAN_STEPS,
    REVIEW_OBSERVATION_MAX_CHARS,
    REVIEW_REPAIR_TIMEOUT_SECONDS,
    REVIEW_SEARCH_MAX_RESULTS,
    REVIEW_SELF_CORRECTION_TIMEOUT_SECONDS,
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
from realmock.platform.capabilities.ai.context.manager import compact_with_summary, upsert_memory_block
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.capabilities.ai.llm.defaults import resolve_context_window, resolve_max_output_tokens
from realmock.platform.capabilities.ai.llm.json_extract import (
    extract_json_object as _extract_json_object,
    salvage_truncated_object as _salvage_truncated_object,
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
_EVIDENCE_CHUNK_CHARS = 12_000
_EVIDENCE_TOTAL_CHARS = 80_000
# Circuit breaker: the exact same call (tool + arguments) failing this many
# times in a row is refused without spending another call. Different arguments
# are never blocked — the workload differs, so the model decides.
_TOOL_CIRCUIT_BREAKER_STREAK = 3

# Final-round wrap-up matching final_round_tool_free=True: the last round is
# sent without a tools parameter, so the copy demands the complete JSON
# directly (unlike the platform _WRAP_UP_HINT, which still allows one last
# essential tool call).
_WRAP_UP_TOOL_FREE_MESSAGE = {
    "role": "system",
    "content": (
        "This is the final round and tools are no longer available. Output the "
        "complete evaluation JSON now: a single JSON object with every required "
        "field, no tool calls, no prose before or after."
    ),
}

# Bounded plan enforcement: the first user message already orders plan-first;
# from the second round on, append a transient reminder at the tail until the
# model declares a plan (tail position keeps the stable prefix cacheable). The
# tool-derived fallback still applies so progress never stalls.
_PLAN_REMINDER_MAX = 3

# Last-resort instruction when the loop burns every round on tools and never
# emits the evaluation: the follow-up call offers no tools, so the model can
# only answer with text. Kept separate from _WRAP_UP_TOOL_FREE_MESSAGE because
# that one closes the in-loop final round while the loop is still running;
# this one drives the post-loop follow-up call after the loop already ended
# empty.
_FORCED_FINAL_INSTRUCTION = (
    "Tools are now disabled. Output the complete resume evaluation as a single "
    "JSON object that matches this schema exactly — same keys, same shapes, "
    "every field present:\n"
    "{schema}\n"
    "Write user-facing fields in {locale}. Use only facts from the conversation "
    "above. Do not invent scores, repos, or quotes. Output JSON only, no tool calls."
)


def _plan_reminder_text() -> str:
    """One-shot prompt builder for the next LLM round when no plan exists."""
    return (
        "Create the review plan now: call review_set_plan before any other tool. "
        f"Declare {REVIEW_MIN_PLAN_STEPS}-{REVIEW_MAX_PLAN_STEPS} steps in the resume's "
        "language; the last step must generate the evaluation JSON. "
        "Then keep the plan in sync with review_update_step as you work."
    )


def _progress_line(round_no: int, tool_calls_used: int) -> str:
    """Per-round budget awareness so the model can pace itself to the answer."""
    return (
        f"Progress: LLM round {round_no}/{REVIEW_MAX_ROUNDS}. "
        f"Tool calls used: {tool_calls_used}/{REVIEW_MAX_TOTAL_TOOL_CALLS} "
        f"(max {REVIEW_MAX_TOOLS_PER_ROUND} per round). Keep enough budget to "
        "finish evidence gathering, then output the final answer."
    )


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


# User-visible progress notices for the post-loop finalize phases (rendered as
# timeline rows by the web UI) so a slow synthesis never looks like a hang.
_FINALIZE_NOTICES: dict[str, tuple[str, str]] = {
    "forced_final": (
        "正在基于已收集的证据汇总生成最终评价…",
        "Synthesizing the final evaluation from the gathered evidence…",
    ),
    "self_correction": (
        "上一轮输出不是有效 JSON，正在重新输出…",
        "The previous output was not valid JSON; re-emitting it…",
    ),
    "repair": (
        "正在基于已收集的证据重建评价 JSON…",
        "Rebuilding the evaluation JSON from the gathered evidence…",
    ),
}


async def _emit_finalize_notice(
    on_event: OnReviewEvent | None,
    locale: str,
    kind: str,
) -> None:
    zh, en = _FINALIZE_NOTICES[kind]
    await _emit(on_event, {"type": "notice", "message": en if locale == "en" else zh})


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


async def _request_json_self_correction(
    llm: LLMClient,
    loop: LoopResult,
    *,
    locale: str,
    parse_error: str,
) -> str | None:
    """One tool-free round asking the model to re-emit its own broken JSON.

    Reuses the loop history (prefix-cache friendly) plus the malformed draft as
    an assistant message and the parser's error message — fixing the model's
    own output beats regenerating from evidence. Bounded by
    ``REVIEW_SELF_CORRECTION_TIMEOUT_SECONDS`` so a hung request still leaves
    time for the repair pass. Never raises; ``None`` sends the caller on to
    the repair pass.
    """
    draft = str(loop.final_content or "").strip()
    if not draft:
        return None
    try:
        # Bounded like the other finalize phases: this call replays the whole
        # loop history over the same flaky network; without an outer bound a
        # hung request could eat the rest of the frontend budget (the
        # transport timeout only caps a single attempt, not its retries).
        text = await asyncio.wait_for(
            llm.chat(
                [
                    *loop.messages,
                    {"role": "assistant", "content": loop.final_content},
                    {
                        "role": "user",
                        "content": (
                            "Your previous reply could not be parsed as JSON. Parser "
                            f"error: {parse_error[:200]}\n"
                            "Output the complete evaluation JSON again: a single JSON "
                            "object matching the required schema exactly, with every "
                            f"field present. Write user-facing fields in {locale}. "
                            "JSON only — no tools, no prose before or after."
                        ),
                    },
                ],
                temperature=REVIEW_AGENT_TEMPERATURE,
            ),
            timeout=REVIEW_SELF_CORRECTION_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning("Resume review JSON self-correction failed: %s", exc)
        return None
    corrected = str(text or "").strip()
    if not corrected:
        return None
    logger.info("Resume review requested a JSON self-correction round (draft %s chars)", len(draft))
    return corrected


async def finalize_review_json(
    loop: LoopResult,
    llm: LLMClient,
    *,
    locale: str,
    max_output: int,
    on_event: OnReviewEvent | None = None,
) -> dict[str, Any]:
    """Parse the loop's final JSON, or repair it through the degradation chain.

    Chain: extract → self-correction (model fixes its own malformed JSON) →
    repair (regenerate from evidence) → salvage (keep the head of a truncated
    reply). Missing evidence → C0001; everything failed → C0002. Each slow
    phase announces itself through ``on_event`` so the live timeline shows
    progress instead of a silent wait.
    """
    payload = _extract_json_object(loop.final_content or "")
    if isinstance(payload, dict):
        return payload
    silent = not str(loop.final_content or "").strip() and not loop.tool_used
    if silent:
        raise_error("C0001")
    # First rung: the model re-emits its own output. Skipped for an empty
    # draft — there is nothing of the model's to fix, go straight to repair.
    draft = str(loop.final_content or "").strip()
    if draft:
        try:
            json.loads(loop.final_content or "")
        except Exception as exc:
            parse_error = f"{type(exc).__name__}: {exc}"
        else:
            parse_error = "no complete JSON object found"
        await _emit_finalize_notice(on_event, locale, "self_correction")
        corrected_text = await _request_json_self_correction(
            llm, loop, locale=locale, parse_error=parse_error
        )
        if corrected_text:
            corrected = _extract_json_object(corrected_text)
            if isinstance(corrected, dict):
                logger.info("Resume review JSON self-correction succeeded")
                return corrected
    logger.info(
        "Resume review final content was not JSON (len=%s); requesting a grounded JSON repair pass",
        len(draft),
    )
    evidence = evidence_for_repair(loop.messages, loop.final_content or "")
    if not evidence.strip():
        raise_error("C0001")
    await _emit_finalize_notice(on_event, locale, "repair")
    # Evidence is char-capped by evidence_for_repair and is sent as-is: a
    # compression round-trip would only add latency and destroy detail the
    # repair needs.
    repaired: Any = None
    repair_error: Exception | None = None
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
                    {"role": "user", "content": evidence},
                ],
                temperature=0.2,
                max_tokens=min(max_output, REVIEW_MAX_OUTPUT_TOKENS),
            ),
            timeout=REVIEW_REPAIR_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning("Resume review JSON repair failed: %s", exc)
        repair_error = exc
    if isinstance(repaired, dict):
        return repaired
    # Last resort for a reply cut off by the output-token cap: the head is real
    # review text, so keep it rather than failing the whole review. Everything
    # past the cut is missing, which the normalizers below fill with defaults.
    salvaged = _salvage_truncated_object(loop.final_content or "")
    if isinstance(salvaged, dict):
        logger.warning(
            "Resume review kept the head of a truncated reply (%s chars, no grounded repair)",
            len(draft),
        )
        return salvaged
    if repair_error is not None:
        raise_error("C0002", cause=repair_error)
    raise_error("C0002")


async def _request_forced_final_answer(
    llm: LLMClient,
    loop: LoopResult,
    *,
    locale: str,
) -> str | None:
    """One tool-free chat call reusing the loop history; None when unusable.

    Covers a loop that broke with tools run but no final content (a failed
    round LLM call, or an empty model reply): without tools the model can only
    answer. Runs under the loop's output-token cap (caller restores the client
    budget afterwards); the transport timeout bounds the call. Never raises —
    failure falls through to the repair path; cancellation still propagates.
    """
    call = llm.chat(
        [
            *loop.messages,
            {
                "role": "system",
                "content": _FORCED_FINAL_INSTRUCTION.format(
                    schema=review_json_schema_text(), locale=locale
                ),
            },
        ],
        temperature=REVIEW_AGENT_TEMPERATURE,
    )
    try:
        text = await call
    except Exception as exc:
        logger.warning("Resume review forced final answer failed: %s", exc)
        return None
    if not str(text or "").strip():
        return None
    logger.info("Resume review loop ended without content; using tool-free final answer")
    return str(text)


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
    budget_state: dict[str, int] | None = None,
    activity_sink: Callable[[str], None] | None = None,
) -> Callable[[str, dict[str, Any]], Awaitable[str]]:
    """Build the Agent-loop ``execute`` callback with SSE progress events.

    ``budget_state["tool_calls"]`` (when given) counts non-plan calls that pass
    the budget gate so the per-round progress line and the total-call refusal
    share one number; circuit-breaker refusals refund their slot.
    ``activity_sink`` receives one compact label per executed non-plan call and
    feeds the deterministic step-note fallback in ``ReviewProcess``.
    Kept as a factory (instead of inline closures) so ``run_resume_review``
    stays orchestration-only and the executor is independently testable.
    """
    tool_seq = 0
    budget = budget_state if budget_state is not None else {"tool_calls": 0}
    # Breaker key: tool + canonical arguments. Only the exact same call is
    # blocked after repeated failures; different arguments stay the model's
    # decision.
    error_streaks: dict[tuple[str, str], int] = {}

    def _args_key(args: dict[str, Any]) -> str:
        try:
            return json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)[:500]
        except Exception:
            return str(args)[:500]

    def _blocked_observation(kind: str, tool: str, message: str) -> str:
        return json.dumps(
            {"error": kind, "tool": tool, "message": message},
            ensure_ascii=False,
        )

    async def execute_tool_call(name: str, args: dict[str, Any]) -> str:
        nonlocal tool_seq
        used_tools.append(name)
        # Plan bookkeeping already arrives as ``plan`` events; do not emit tool_step.
        if name.startswith(PLAN_TOOL_PREFIX):
            raw, _status = await _invoke_review_tool(bundle, name, args, context)
            return raw
        if budget["tool_calls"] >= REVIEW_MAX_TOTAL_TOOL_CALLS:
            # Soft ceiling: refuse the call, keep the loop alive so the model
            # can always write its final answer.
            return _blocked_observation(
                "tool_budget_exhausted",
                name,
                f"Tool-call budget exhausted ({REVIEW_MAX_TOTAL_TOOL_CALLS} calls). "
                "Write the final answer with the evidence already gathered.",
            )
        # Reserve the slot before the first await point: every call in a
        # parallel round passes the check above, and an after-the-fact
        # increment would let them jointly overshoot the soft ceiling.
        # Circuit-blocked calls below refund it — they never reach the
        # provider, so they cost no budget.
        budget["tool_calls"] += 1
        key = (name, _args_key(args))
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
        if error_streaks.get(key, 0) >= _TOOL_CIRCUIT_BREAKER_STREAK:
            budget["tool_calls"] -= 1  # refusal costs no provider budget
            raw, status = _blocked_observation(
                "circuit_open",
                name,
                f"This exact call ({name} with the same arguments) failed "
                f"{_TOOL_CIRCUIT_BREAKER_STREAK} times in a row and is temporarily "
                "blocked. Change the arguments, use a different tool, or move on "
                "to writing the final answer.",
            ), "error"
        else:
            raw, status = await _invoke_review_tool(bundle, name, args, context)
            if status == "error":
                error_streaks[key] = error_streaks.get(key, 0) + 1
            else:
                error_streaks.pop(key, None)
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
    budget_state = {"tool_calls": 0}
    execute_tool_call = _build_tool_executor(
        bundle,
        used_tools,
        on_event,
        error_context,
        budget_state,
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
            suffix.append({"role": "system", "content": _plan_reminder_text()})
        if process.steps and all(
            step.status in ("done", "skipped") for step in process.steps
        ):
            # The plan is finished but the model is still calling tools: pin a
            # strong finalize instruction until it produces the answer.
            suffix.append(
                {
                    "role": "system",
                    "content": (
                        "All plan steps are complete. Output the complete "
                        "evaluation JSON as your final answer now — no further "
                        "tool calls."
                    ),
                }
            )
        suffix.append(
            {
                "role": "system",
                "content": _progress_line(round_index + 1, budget_state["tool_calls"]),
            }
        )
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
            wrap_up_hint=_WRAP_UP_TOOL_FREE_MESSAGE,
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
