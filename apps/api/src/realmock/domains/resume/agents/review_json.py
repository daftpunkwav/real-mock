"""Resume-review JSON finalize chain: extract → self-correction → repair → salvage.

Everything between "the agent loop ended" and "a review dict exists" lives
here, including the evidence assembly the grounded repair pass is built from.
Each slow phase announces itself on the live timeline so a long synthesis
never looks like a hang. Copy blocks come from ``review_prompts.py``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from realmock.domains.resume.agents.review_prompts import _emit_finalize_notice
from realmock.domains.resume.prompts import (
    REVIEW_FORCED_FINAL_INSTRUCTION,
    review_json_schema_text,
    review_repair_system,
    review_self_correction_user,
)
from realmock.domains.resume.schemas.limits import (
    REVIEW_AGENT_TEMPERATURE,
    REVIEW_MAX_OUTPUT_TOKENS,
    REVIEW_REPAIR_TIMEOUT_SECONDS,
    REVIEW_SELF_CORRECTION_TIMEOUT_SECONDS,
)
from realmock.platform.capabilities.ai.agent import LoopResult, OnAgentEvent
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.capabilities.ai.llm.json_extract import (
    extract_json_object as _extract_json_object,
    salvage_truncated_object as _salvage_truncated_object,
    truncate_chunk,
)
from realmock.platform.core.errors import raise_error

logger = logging.getLogger(__name__)

# Defense-in-depth caps: repair evidence joins already-compacted tool
# observations; these only bound the join itself.
_EVIDENCE_CHUNK_CHARS = 12_000
_EVIDENCE_TOTAL_CHARS = 80_000


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
                        "content": review_self_correction_user(parse_error, locale),
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
    on_event: OnAgentEvent | None = None,
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
    # repair needs. Two fresh samples: empty replies recur on reasoning-heavy
    # models, and this pass runs only when everything above already failed —
    # the retry lands exclusively on runs that would otherwise raise C0002.
    repaired: Any = None
    repair_error: Exception | None = None
    for attempt in range(2):
        try:
            repaired = await asyncio.wait_for(
                llm.chat_json(
                    [
                        {
                            "role": "system",
                            "content": review_repair_system(locale),
                        },
                        {"role": "user", "content": evidence},
                    ],
                    temperature=0.2,
                    max_tokens=min(max_output, REVIEW_MAX_OUTPUT_TOKENS),
                ),
                timeout=REVIEW_REPAIR_TIMEOUT_SECONDS,
            )
            break
        except Exception as exc:
            logger.warning("Resume review JSON repair failed (attempt %s/2): %s", attempt + 1, exc)
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
    """Up to two tool-free chat calls reusing the loop history; None when unusable.

    Covers a loop that broke with tools run but no final content (a failed
    round LLM call, or an empty model reply): without tools the model can only
    answer. Empty replies recur on reasoning-heavy models, so a blank result
    gets one fresh sample instead of failing the run. Runs under the loop's
    output-token cap (caller restores the client budget afterwards); the
    caller's wait_for bounds the total, so a hung request still leaves time
    for the lighter repair pass before the frontend budget ends the run.
    Never raises — failure falls through to the repair path; cancellation
    still propagates.
    """
    messages = [
        *loop.messages,
        {
            "role": "system",
            "content": REVIEW_FORCED_FINAL_INSTRUCTION.format(
                schema=review_json_schema_text(), locale=locale
            ),
        },
    ]
    for attempt in range(2):
        try:
            text = await llm.chat(messages, temperature=REVIEW_AGENT_TEMPERATURE)
        except Exception as exc:
            logger.warning("Resume review forced final answer failed: %s", exc)
            return None
        if str(text or "").strip():
            logger.info("Resume review loop ended without content; using tool-free final answer")
            return str(text)
        logger.warning(
            "Resume review forced final answer came back empty (attempt %s/2)", attempt + 1
        )
    return None
