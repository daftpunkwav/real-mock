"""Compatibility conversion from one legacy ``LLMSettings`` row to three ``StageConfig`` stages.

Initial upgrade path (``migrate_legacy_to_stages``): split the legacy settings into three
stage rows—recognize / reason / speak; stages already configured are not overwritten.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from realmock.platform.capabilities.ai.llm.defaults import (
    SPEECH_STAGE_CONTEXT_WINDOW,
    SPEECH_STAGE_MAX_OUTPUT_TOKENS,
    SPEECH_STAGE_TTS_MAX_OUTPUT_TOKENS,
)
from realmock.platform.core.constants import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_LLM_PROTOCOL,
    DEFAULT_MAX_OUTPUT_TOKENS,
    PipelineStage,
)
from realmock.platform.models import LLMSettings, StageConfig
from realmock.platform.services.pipeline.secrets import maybe_encrypt
from realmock.platform.services.pipeline.stages import get_or_create_stage_config


def get_llm_settings_row(db: Session) -> LLMSettings | None:
    """Read a single row from api library ``llm_settings`` (legacy table before migration)."""
    return db.query(LLMSettings).filter(LLMSettings.id == 1).first()


def _reason_config_from_legacy(row: LLMSettings) -> dict[str, Any]:
    return {
        "stage": PipelineStage.REASON,
        "provider": row.provider or "",
        "api_base": row.api_base or "",
        "api_key": row.api_key or "",
        "protocol": getattr(row, "protocol", DEFAULT_LLM_PROTOCOL) or DEFAULT_LLM_PROTOCOL,
        "model": row.model or "",
        "max_tokens": row.max_tokens,
        "context_window": row.context_window,
        "capabilities": {
            "supports_vision": bool(getattr(row, "supports_vision", True)),
            "supports_audio_input": bool(getattr(row, "supports_audio", False)),
            "supports_audio_output": True,
            "supports_video_input": bool(getattr(row, "supports_vision", False)),
        },
        "fallback": {"handler": "", "mode": ""},
        "extras": {},
    }


def _recognize_config_from_legacy(row: LLMSettings) -> dict[str, Any]:
    return {
        "stage": PipelineStage.RECOGNIZE,
        "provider": row.speech_recognize_handler or "local",
        "api_base": row.asr_api_base or "",
        "api_key": row.asr_api_key or "",
        "protocol": DEFAULT_LLM_PROTOCOL,
        "model": row.asr_model or row.stt_model or "",
        "max_tokens": SPEECH_STAGE_MAX_OUTPUT_TOKENS,
        "context_window": SPEECH_STAGE_CONTEXT_WINDOW,
        "capabilities": {
            "supports_vision": False,
            "supports_audio_input": True,
            "supports_audio_output": False,
            "supports_video_input": False,
        },
        "fallback": {"handler": "local", "mode": "transcribe"},
        "extras": {
            "speech_recognize_mode": row.speech_recognize_mode or "transcribe",
            "asr_app_id": row.asr_app_id or "",
            "asr_api_secret": row.asr_api_secret or "",
            "asr_access_key": row.asr_access_key or "",
            "asr_resource_id": row.asr_resource_id or "",
            "asr_app_key": row.asr_app_key or "",
        },
    }


def _speak_config_from_legacy(row: LLMSettings) -> dict[str, Any]:
    return {
        "stage": PipelineStage.SPEAK,
        "provider": row.speech_speak_handler or "edge",
        "api_base": row.tts_api_base or "",
        "api_key": row.tts_api_key or "",
        "protocol": DEFAULT_LLM_PROTOCOL,
        "model": row.tts_model or "",
        "max_tokens": SPEECH_STAGE_TTS_MAX_OUTPUT_TOKENS,
        "context_window": SPEECH_STAGE_CONTEXT_WINDOW,
        "capabilities": {
            "supports_vision": False,
            "supports_audio_input": False,
            "supports_audio_output": True,
            "supports_video_input": False,
        },
        "fallback": {"handler": "edge", "mode": "tts_from_text"},
        "extras": {
            "speech_speak_mode": row.speech_speak_mode or "tts_from_text",
            "tts_voice": row.tts_voice or "zh-CN-XiaoxiaoNeural",
        },
    }


def migrate_legacy_to_stages(db: Session) -> dict[str, StageConfig]:
    """First upgrade: Split old LLMSettings into three-stage stage_configs."""
    legacy = get_llm_settings_row(db)
    configs: dict[str, StageConfig] = {}
    for stage, builder in [
        (PipelineStage.RECOGNIZE, _recognize_config_from_legacy),
        (PipelineStage.REASON, _reason_config_from_legacy),
        (PipelineStage.SPEAK, _speak_config_from_legacy),
    ]:
        row = get_or_create_stage_config(db, stage)
        if legacy is None:
            configs[stage] = row
            continue
        if row.provider or row.api_base or row.model or row.api_key:
            configs[stage] = row
            continue
        data = builder(legacy)
        row.provider = data.get("provider") or ""
        row.api_base = data.get("api_base") or ""
        row.api_key = maybe_encrypt(data.get("api_key"), row.api_key or "")
        row.protocol = data.get("protocol") or DEFAULT_LLM_PROTOCOL
        row.model = data.get("model") or ""
        row.max_tokens = data.get("max_tokens") or DEFAULT_MAX_OUTPUT_TOKENS
        row.context_window = data.get("context_window") or DEFAULT_CONTEXT_WINDOW
        caps = data.get("capabilities") or {}
        row.supports_vision = bool(caps.get("supports_vision"))
        row.supports_audio_input = bool(caps.get("supports_audio_input"))
        row.supports_audio_output = bool(caps.get("supports_audio_output"))
        row.supports_video_input = bool(caps.get("supports_video_input"))
        fb = data.get("fallback") or {}
        row.fallback_handler = fb.get("handler") or ""
        row.fallback_mode = fb.get("mode") or ""
        row.extras = json.dumps(data.get("extras") or {}, ensure_ascii=False)
        row.updated_at = datetime.now(timezone.utc)
        configs[stage] = row
    db.commit()
    for row in configs.values():
        db.refresh(row)
    return configs
