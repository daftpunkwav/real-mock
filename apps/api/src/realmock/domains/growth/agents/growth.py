"""Rule-based GrowthAgent: aggregate history into page-level stats."""

from __future__ import annotations

import json
import logging
from typing import Any

from realmock.domains.growth.models.growth import GrowthRecord

logger = logging.getLogger(__name__)


def _as_str_list(raw: Any) -> list[str]:
    """Normalize weak_skills / training_plan from ORM str or already-parsed list."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x is not None and str(x).strip()]
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
        if isinstance(data, list):
            return [str(x) for x in data if x is not None and str(x).strip()]
        return []
    return []


class GrowthAgent:
    """Aggregate growth records into stats (mirrors frontend ``growthStats.ts``)."""

    def analyze(
        self,
        records: list[GrowthRecord] | list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return top weaknesses, interview counts, total_plans/total_weak_skills/growth_pct, and growth level labels."""
        count: dict[str, int] = {}
        total_plans = 0
        for r in records:
            if isinstance(r, dict):
                weak = _as_str_list(r.get("weak_skills"))
                plans = _as_str_list(r.get("training_plan"))
            else:
                weak = _as_str_list(r.weak_skills)
                plans = _as_str_list(r.training_plan)
            for w in weak:
                count[w] = count.get(w, 0) + 1
            total_plans += len(plans)

        top_weaknesses = sorted(count.items(), key=lambda kv: kv[1], reverse=True)[:5]
        total_interviews = len(records)
        total_weak_skills = len(count)
        growth_pct = min(100, total_interviews * 25 + min(total_plans, 4) * 5)
        if total_interviews == 0:
            growth_level = "To be started"
        elif total_interviews < 3:
            growth_level = "Starting stage"
        elif total_interviews < 6:
            growth_level = "Continuous growth"
        else:
            growth_level = "Advanced promotion"

        return {
            "top_weaknesses": [[w, n] for w, n in top_weaknesses],
            "total_interviews": total_interviews,
            "total_plans": total_plans,
            "total_weak_skills": total_weak_skills,
            "growth_pct": growth_pct,
            "growth_level": growth_level,
        }
