"""LLM growth-insight agent: cross-session analysis via a bounded tool loop.

Unlike a single-shot call, the agent starts from a small session index and
pulls per-session reports / resume / profile evidence on demand — truncating
inputs up front would trade facts for context space, and the loop lets the
model spend attention where the signal is.

Robustness mirrors the resume-review loop: per-tool timeout, same-args circuit
breaker, tool-call budget with budget-aware progress lines, countdown nudges,
and a tool-free final round (protocol-level guarantee that the JSON lands).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.growth.agents.tools import history_tool_specs
from realmock.domains.growth.prompts import (
    GROWTH_INSIGHT_SYSTEM,
    GROWTH_MAX_ROUNDS,
    GROWTH_MAX_TOOLS_PER_ROUND,
    GROWTH_MAX_TOTAL_TOOL_CALLS,
    GROWTH_WRAP_UP_TOOL_FREE_MESSAGE,
    growth_insight_user_message,
)
from realmock.platform.capabilities.ai.agent import run_agent_loop
from realmock.platform.capabilities.ai.agent.tools import ToolBundle
from realmock.platform.capabilities.ai.agent.tools.executor import (
    ToolRunGuard,
    invoke_with_timeout,
)
from realmock.platform.capabilities.ai.agent.tools.profile import (
    profile_from_orm,
    profile_tool_specs,
)
from realmock.platform.capabilities.ai.agent.tools.resume import (
    resume_tool_specs,
    snapshot_from_payload,
)
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.capabilities.ai.llm.client.base import LLMUpstreamError
from realmock.platform.capabilities.ai.llm.json_extract import (
    extract_json_object as _extract_json_object,
    salvage_truncated_object as _salvage_truncated_object,
)
from realmock.platform.contracts.session_catalog import get_session_catalog
from realmock.platform.services.candidate_read import (
    get_default_user_profile,
    get_resume_agent_payload,
)

logger = logging.getLogger(__name__)

GROWTH_INSIGHT_TEMPERATURE = 0.2
# Hard wall around the whole loop: the regen runs as a background task, so
# this only bounds a pathological hang (LLM attempts retry internally; a hung
# request would otherwise hold the single-flight slot forever).
GROWTH_LOOP_TIMEOUT_SECONDS = 480.0
# Same-args circuit breaker (resume-review parity): the exact same call
# failing this many times in a row is refused without spending another call.
_TOOL_CIRCUIT_BREAKER_STREAK = 3
_TOOL_TIMEOUT_SECONDS = 20.0

_VALID_STAGES = ("rising", "stalling", "plateau", "insufficient")


def _clamp_int(value: Any, low: int, high: int, default: int = 0) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _as_str_list(raw: Any, *, cap: int, item_max: int = 300) -> list[str]:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text:
            out.append(text[:item_max])
        if len(out) >= cap:
            break
    return out


def normalize_growth_insight(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate/clamp the model JSON into the growth-insight contract."""
    stage = str(payload.get("trajectory_stage") or "").strip().lower()
    if stage not in _VALID_STAGES:
        stage = "insufficient"

    weaknesses: list[dict[str, Any]] = []
    raw_weak = payload.get("recurring_weaknesses")
    if isinstance(raw_weak, list):
        for item in raw_weak:
            if not isinstance(item, dict):
                continue
            skill = str(item.get("skill") or "").strip()
            if not skill:
                continue
            trend = str(item.get("trend") or "stable").strip().lower()
            weaknesses.append(
                {
                    "skill": skill[:120],
                    "count": _clamp_int(item.get("count"), 1, 999, 1),
                    "trend": trend if trend in ("worsening", "stable", "improving") else "stable",
                    "advice": str(item.get("advice") or "").strip()[:400],
                }
            )
            if len(weaknesses) >= 6:
                break

    plan: list[dict[str, Any]] = []
    raw_plan = payload.get("training_plan")
    if isinstance(raw_plan, list):
        for item in raw_plan:
            if not isinstance(item, dict):
                continue
            area = str(item.get("area") or "").strip()
            actions = _as_str_list(item.get("actions"), cap=4, item_max=240)
            if not area or not actions:
                continue
            plan.append(
                {
                    "area": area[:120],
                    "based_on": str(item.get("based_on") or "").strip()[:300],
                    "actions": actions,
                }
            )
            if len(plan) >= 4:
                break

    return {
        "headline": str(payload.get("headline") or "").strip()[:200],
        "trajectory": str(payload.get("trajectory") or "").strip()[:1200],
        "trajectory_stage": stage,
        "recurring_weaknesses": weaknesses,
        "improving_areas": _as_str_list(payload.get("improving_areas"), cap=6),
        "resume_gap_insights": _as_str_list(payload.get("resume_gap_insights"), cap=6),
        "training_plan": plan,
    }


def _insight_is_substantive(insight: dict[str, Any]) -> bool:
    """Reject empty shells (model returned the schema with no analysis)."""
    return bool(insight["trajectory"] and insight["headline"]) and bool(
        insight["recurring_weaknesses"] or insight["improving_areas"] or insight["training_plan"]
    )


def _build_session_index(sessions_db: Session, *, limit: int = 20) -> list[dict[str, Any]]:
    """Compact scored-session index (the model expands via history tools)."""
    catalog = get_session_catalog()
    rows = []
    for item in catalog.list_sessions(sessions_db):
        if item.overall_score is None:
            continue
        ended = item.ended_at or item.created_at
        rows.append(
            {
                "session_id": int(item.id or 0),
                "date": ended.strftime("%Y-%m-%d") if ended else "",
                "role": item.role or "",
                "company": item.company or "",
                "level": item.level or "",
                "overall_score": item.overall_score,
                "verdict": item.result,
            }
        )
        if len(rows) >= limit:
            break
    return rows


def build_growth_bundle(api_db: Session, sessions_db: Session) -> ToolBundle:
    """Compose the growth evidence bundle from shared platform tool factories."""
    bundle = ToolBundle()
    bundle.extend(history_tool_specs(sessions_db))
    payload = get_resume_agent_payload(api_db, _latest_scored_resume_id(api_db))
    if payload is not None:
        bundle.extend(resume_tool_specs(snapshot_from_payload(payload)))
    profile = profile_from_orm(get_default_user_profile(api_db))
    if profile is not None and getattr(profile, "fields", None):
        bundle.extend(profile_tool_specs(profile))
    return bundle


def _latest_scored_resume_id(api_db: Session) -> int | None:
    """Newest active scored resume, else newest scored (platform model read)."""
    from realmock.platform.models import Resume

    row = (
        api_db.query(Resume)
        .filter(Resume.is_active.is_(True), Resume.score.isnot(None))
        .order_by(Resume.id.desc())
        .first()
    )
    if row is None:
        row = (
            api_db.query(Resume)
            .filter(Resume.score.isnot(None))
            .order_by(Resume.created_at.desc(), Resume.id.desc())
            .first()
        )
    return int(row.id) if row is not None else None


def _extract_analysis_json(text: str | None) -> dict[str, Any] | None:
    """Pull the analysis JSON out of the loop's final content (or None)."""
    draft = str(text or "").strip()
    if not draft:
        return None
    extracted = _extract_json_object(draft)
    if isinstance(extracted, dict):
        return extracted
    salvaged = _salvage_truncated_object(draft)
    return salvaged if isinstance(salvaged, dict) else None


async def generate_growth_insight(
    api_db: Session,
    sessions_db: Session,
    *,
    locale: str = "zh-CN",
) -> tuple[dict[str, Any], int] | None:
    """Generate the cross-session growth insight, or None on any failure.

    Returns ``(insight, session_count)`` — the count of scored sessions the
    analysis is based on (callers persist it alongside the payload).
    """
    index = _build_session_index(sessions_db)
    if not index:
        logger.info("growth insight skipped: no scored sessions yet")
        return None
    session_count = len(index)

    llm = LLMClient.from_db(api_db)
    bundle = build_growth_bundle(api_db, sessions_db)

    def _budget_refusal(name: str, limit: int) -> str:
        return json.dumps(
            {
                "error": "tool_budget_exhausted",
                "message": (
                    f"Tool-call budget exhausted ({limit} calls). "
                    "Write the final analysis with the evidence already gathered."
                ),
            },
            ensure_ascii=False,
        )

    def _circuit_refusal(name: str, streak: int) -> str:
        return json.dumps(
            {
                "error": "circuit_open",
                "message": (
                    f"This exact call failed {streak} times in a row and is "
                    "temporarily blocked. Change the arguments, use a different "
                    "tool, or move on to writing the final analysis."
                ),
            },
            ensure_ascii=False,
        )

    guard = ToolRunGuard(
        max_total_calls=GROWTH_MAX_TOTAL_TOOL_CALLS,
        circuit_streak=_TOOL_CIRCUIT_BREAKER_STREAK,
        budget_refusal=_budget_refusal,
        circuit_refusal=_circuit_refusal,
    )

    async def execute_tool_call(name: str, args: dict[str, Any]) -> str:
        refusal = guard.acquire(name, args)
        if refusal is not None:
            return refusal
        raw, status = await invoke_with_timeout(
            bundle,
            name,
            args,
            timeout=_TOOL_TIMEOUT_SECONDS,
            context={"domain": "growth"},
        )
        guard.report(name, args, failed=(status == "error"))
        return raw


    messages = [
        {"role": "system", "content": GROWTH_INSIGHT_SYSTEM},
        {
            "role": "user",
            "content": growth_insight_user_message(
                session_index_json=json.dumps(index, ensure_ascii=False),
                locale=locale,
            ),
        },
    ]

    try:
        loop = await asyncio.wait_for(
            run_agent_loop(
                llm,
                messages,
                tools=bundle.definitions(),
                execute=execute_tool_call,
                max_rounds=GROWTH_MAX_ROUNDS,
                max_tools_per_round=GROWTH_MAX_TOOLS_PER_ROUND,
                temperature=GROWTH_INSIGHT_TEMPERATURE,
                drift_retry=True,
                wrap_up_hint=GROWTH_WRAP_UP_TOOL_FREE_MESSAGE,
                countdown_rounds=4,
                round_retries=1,
                final_round_tool_free=True,
                error_context={"domain": "growth"},
            ),
            timeout=GROWTH_LOOP_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("growth insight loop timed out after %ss", GROWTH_LOOP_TIMEOUT_SECONDS)
        return None
    except LLMUpstreamError as exc:
        logger.warning("growth insight LLM upstream failure: %s", exc)
        return None
    except Exception:
        logger.exception("growth insight generation failed")
        return None

    raw_payload = _extract_analysis_json(loop.final_content)
    if not isinstance(raw_payload, dict):
        logger.warning(
            "growth insight produced no parseable JSON (rounds used, final len=%s)",
            len(str(loop.final_content or "")),
        )
        return None
    insight = normalize_growth_insight(raw_payload)
    if not _insight_is_substantive(insight):
        logger.warning("growth insight lacks substance; discarded")
        return None
    return insight, session_count


__all__ = [
    "GROWTH_LOOP_TIMEOUT_SECONDS",
    "build_growth_bundle",
    "generate_growth_insight",
    "normalize_growth_insight",
]
