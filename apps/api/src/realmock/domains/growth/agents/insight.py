"""LLM growth-insight agent: cross-session analysis from report digests.

Single ``chat_json`` round (no tool loop): the input is already structured and
bounded, so a ReAct cycle would add latency without adding information.
Failures degrade to ``None`` — the ingest path must never crash.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.growth.prompts import GROWTH_INSIGHT_SYSTEM, growth_insight_user_message
from realmock.domains.growth.services.context_builder import build_growth_context
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.capabilities.ai.llm.client.base import LLMUpstreamError

logger = logging.getLogger(__name__)

GROWTH_INSIGHT_TIMEOUT_SECONDS = 180.0
GROWTH_INSIGHT_TEMPERATURE = 0.2

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
    return bool(
        insight["trajectory"] and insight["headline"]
    ) and bool(insight["recurring_weaknesses"] or insight["improving_areas"] or insight["training_plan"])


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
    context = build_growth_context(sessions_db, api_db)
    sessions = context["sessions"]
    if not sessions:
        logger.info("growth insight skipped: no scored sessions yet")
        return None
    session_count = len(sessions)

    llm = LLMClient.from_db(api_db)
    messages = [
        {"role": "system", "content": GROWTH_INSIGHT_SYSTEM},
        {
            "role": "user",
            "content": growth_insight_user_message(
                sessions_json=json.dumps(sessions, ensure_ascii=False),
                resume_summary=context["resume_summary"],
                profile_summary=context["profile_summary"],
                locale=locale,
            ),
        },
    ]
    try:
        raw = await asyncio.wait_for(
            llm.chat_json(messages, temperature=GROWTH_INSIGHT_TEMPERATURE),
            timeout=GROWTH_INSIGHT_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("growth insight timed out after %ss", GROWTH_INSIGHT_TIMEOUT_SECONDS)
        return None
    except LLMUpstreamError as exc:
        logger.warning("growth insight LLM upstream failure: %s", exc)
        return None
    except Exception:
        logger.exception("growth insight generation failed")
        return None

    if not isinstance(raw, dict):
        logger.warning("growth insight returned non-dict payload (%s)", type(raw).__name__)
        return None
    insight = normalize_growth_insight(raw)
    if not _insight_is_substantive(insight):
        logger.warning("growth insight lacks substance; discarded")
        return None
    return insight, session_count


__all__ = [
    "GROWTH_INSIGHT_TIMEOUT_SECONDS",
    "generate_growth_insight",
    "normalize_growth_insight",
]
