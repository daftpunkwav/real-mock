"""Voice provider catalog and stage-credential isolation regressions."""

from __future__ import annotations

from realmock.platform.capabilities.voice.config.catalog import catalog_payload, find_provider
from realmock.platform.capabilities.voice.config.credentials import build_stt_credentials


def test_catalog_has_three_stages_and_zhipu_coming_soon():
    cat = catalog_payload()
    assert "reasoning" in cat and "recognize" in cat and "speak" in cat
    zhipu = find_provider("recognize", "zhipu_glm4_voice")
    assert zhipu is not None
    assert zhipu["status"] == "coming_soon"
    assert zhipu["recognize_via"] == "native_audio"
    speak_edge = find_provider("speak", "edge")
    assert speak_edge and speak_edge["status"] == "ready"
    mm = find_provider("reasoning", "minimax")
    assert mm and mm["can_interview_reason"]


def test_build_stt_never_uses_reason_key():
    """Isolate recognition credentials from the reasoning Key: when the recognize stage has no configured key, never fall back to the reason stage."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from realmock.platform.core.constants import PipelineStage
    from realmock.platform.database import ApiBase
    from realmock.platform.schemas import StageConfigUpdate, StageModelCapability
    from realmock.platform.services.pipeline.config import (
        get_stage_config_for_runtime,
        update_stage_config,
    )

    eng = create_engine("sqlite://", future=True)
    ApiBase.metadata.create_all(eng)
    factory = sessionmaker(bind=eng, expire_on_commit=False)
    db = factory()
    try:
        update_stage_config(
            db,
            PipelineStage.REASON,
            StageConfigUpdate(
                provider="minimax",
                api_base="https://api.minimaxi.com/v1",
                api_key="sk-minimax-thinking-key",
                model="abab-test",
            ),
        )
        update_stage_config(
            db,
            PipelineStage.RECOGNIZE,
            StageConfigUpdate(
                provider="openai_compat",
                api_base="https://api.siliconflow.cn/v1",
                api_key="",
                model="FunAudioLLM/SenseVoiceSmall",
                capabilities=StageModelCapability(supports_audio_input=True),
            ),
        )

        creds = build_stt_credentials(get_stage_config_for_runtime(db, PipelineStage.RECOGNIZE))
        assert creds.provider == "openai_compat"
        assert creds.api_key == ""
        assert creds.api_key != "sk-minimax-thinking-key"
    finally:
        db.close()
