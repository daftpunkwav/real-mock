"""Model entry connectivity test routing (separate from CRUD)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from realmock.platform.core.constants import DEFAULT_LLM_RATE_LIMIT_PER_MINUTE
from realmock.platform.core.ratelimit import rate_limit_dep
from realmock.platform.database import get_db
from realmock.domains.settings.services.model_registry import get_profile
from realmock.domains.settings.services.route_timing import run_timed_stage_test
from realmock.domains.settings.services.stage_tests import test_recognize, test_reason, test_speak

router = APIRouter()


@router.post(
    "/test/model/{model_id}",
    dependencies=[Depends(rate_limit_dep(key="llm", limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE))],
)
async def test_model(model_id: int, db: Session = Depends(get_db)) -> dict:
    """Selects test pipelines based on capabilities declared by model entries; does not change current task bindings."""
    profile = get_profile(db, model_id)
    if profile.cap_audio_in:
        return await run_timed_stage_test(test_recognize(db, profile_id=model_id))
    if profile.cap_audio_out:
        return await run_timed_stage_test(test_speak(db, profile_id=model_id))
    return await run_timed_stage_test(test_reason(db, profile_id=model_id))
