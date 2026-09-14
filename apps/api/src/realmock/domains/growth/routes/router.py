"""Growth domain HTTP API (history, insights, aggregated stats)."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from realmock.domains.growth.agents.growth import GrowthAgent
from realmock.domains.growth.models.growth import GrowthRecord
from realmock.domains.growth.services.learning import get_system_insights
from realmock.platform.database import get_sessions_db

logger = logging.getLogger(__name__)
router = APIRouter()

_HISTORY_LIMIT = 20
_AGGREGATED_LIMIT = 50


def _safe_json_list(raw: str | None, *, field: str, record_id: int) -> list[Any]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "GrowthRecord.%s parse failed id=%s; degraded to empty list",
            field,
            record_id,
        )
        return []


@router.get("/history")
def get_growth_history(db: Session = Depends(get_sessions_db)) -> list[dict[str, Any]]:
    records = db.query(GrowthRecord).order_by(GrowthRecord.created_at.desc()).limit(_HISTORY_LIMIT).all()
    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "weak_skills": _safe_json_list(r.weak_skills, field="weak_skills", record_id=r.id),
            "training_plan": _safe_json_list(
                r.training_plan, field="training_plan", record_id=r.id
            ),
            "created_at": r.created_at,
        }
        for r in records
    ]


@router.get("/system-insights")
def get_system_growth_insights() -> dict[str, Any]:
    """System-level self-growth insights (cross-interview aggregates)."""
    from realmock.platform.capabilities.integrations.github.token_store import has_stored_token
    from realmock.platform.config import get_settings

    insights = get_system_insights(limit=15)
    # The growth page renders a GitHub-linkage hint from this flag; a stored
    # credential or process-env token both count as configured.
    settings = get_settings()
    insights["github_token_configured"] = bool(has_stored_token() or settings.github_token)
    return insights


@router.get("/aggregated")
def get_aggregated_growth_stats(db: Session = Depends(get_sessions_db)) -> dict[str, Any]:
    """Aggregated growth stats computed on request (frontend can drop ``computeGrowthStats``)."""
    records = db.query(GrowthRecord).order_by(GrowthRecord.created_at.desc()).limit(_AGGREGATED_LIMIT).all()
    return GrowthAgent().analyze(records)


__all__ = ["router", "_safe_json_list"]
