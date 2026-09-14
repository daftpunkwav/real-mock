"""BYOK settings API for the three processors.

Security notes:

- Validate URL format when updating ``api_base`` (http(s), with https required in prod; SSRF network-range validation runs at runtime);
- Encrypt Keys with AES-256-GCM before storing them;
- Keep recognition credentials separate from the reasoning Key; silent reuse is forbidden.

For routes in the model-entry system (provider / model / task binding), see ``realmock.domains.settings.routes.models``;
for DB reads/writes, see ``realmock.domains.settings.services.model_registry``.

Responsibility split:
- URL format and stage-provider validation: :mod:`realmock.domains.settings.services.validation`;
- Three-stage connectivity tests: :mod:`realmock.domains.settings.services.stage_tests`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from realmock.platform.core.constants import DEFAULT_LLM_RATE_LIMIT_PER_MINUTE, PipelineStage
from realmock.platform.core.errors import raise_error
from realmock.platform.core.ratelimit import rate_limit_dep
from realmock.platform.database import get_db
from realmock.platform.schemas import (
    LLMTestResponse,
    StageConfigResponse,
    StageConfigsResponse,
    StageConfigUpdate,
)
from realmock.platform.capabilities.voice.config.catalog import catalog_payload
from realmock.platform.services.pipeline.config import (
    get_stage_config_map,
    stage_to_response,
    update_stage_config,
)
from realmock.domains.settings.services.route_timing import run_timed_stage_test
from realmock.domains.settings.services.validation import safe_base, validate_stage_config
from realmock.domains.settings.services.stage_tests import test_recognize, test_reason, test_speak

router = APIRouter()


@router.get("/catalog")
def get_voice_catalog() -> dict[str, Any]:
    """Three-stage supplier capability catalog."""
    return catalog_payload()


@router.get("/stages", response_model=StageConfigsResponse)
def get_stage_configs(db: Session = Depends(get_db)):
    """Read three-stage configs."""
    cfg_map = get_stage_config_map(db)
    return StageConfigsResponse(
        recognize=StageConfigResponse(**cfg_map["recognize"]),
        reason=StageConfigResponse(**cfg_map["reason"]),
        speak=StageConfigResponse(**cfg_map["speak"]),
        updated_at=cfg_map["reason"].get("updated_at"),
    )


@router.put("/stages/{stage}", response_model=StageConfigResponse)
def update_stage(
    stage: str,
    body: StageConfigUpdate,
    db: Session = Depends(get_db),
):
    """Save one stage config."""
    stage = (stage or "").strip().lower()
    if stage not in (PipelineStage.RECOGNIZE, PipelineStage.REASON, PipelineStage.SPEAK):
        raise_error("A4004")

    safe_base(body.api_base, label=f"{stage} API")
    validate_stage_config(stage, body)

    row = update_stage_config(db, stage, body)
    return StageConfigResponse(**stage_to_response(row))


@router.post(
    "/test/{stage}",
    response_model=LLMTestResponse,
    dependencies=[Depends(rate_limit_dep(key="llm", limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE))],
)
async def test_pipeline_stage(stage: str, db: Session = Depends(get_db)):
    """Three-stage connectivity test: recognize | reason | speak."""
    stage = (stage or "").strip().lower()
    if stage == "recognize":
        result = await run_timed_stage_test(test_recognize(db))
    elif stage in ("reason", "reasoning", "llm"):
        result = await run_timed_stage_test(test_reason(db))
    elif stage in ("speak", "tts"):
        result = await run_timed_stage_test(test_speak(db))
    else:
        raise_error("A4004")

    return LLMTestResponse(
        success=bool(result.get("success")),
        message=str(result.get("message") or ""),
        model=result.get("model"),
        transcript=result.get("transcript"),
        audio_base64=result.get("audio_base64"),
        fallback=result.get("fallback"),
        latency_ms=result.get("latency_ms"),
    )
