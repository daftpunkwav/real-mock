"""ORM models for infrastructure/handler configuration.

StageConfig / LLMSettings are shared handler configuration tables used across services and do not belong to any business domain.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from realmock.platform.core.constants import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_LLM_PROTOCOL,
    DEFAULT_MAX_OUTPUT_TOKENS,
)
from realmock.platform.database import ApiBase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StageConfig(ApiBase):
    """Independent configuration for the three processing stages: recognize / reason / speak.

    Each record corresponds to one stage and supports custom providers, API formats, model capabilities, etc.
    """

    __tablename__ = "stage_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), default="")
    api_base: Mapped[str] = mapped_column(String(500), default="")
    api_key: Mapped[str] = mapped_column(String(500), default="")
    protocol: Mapped[str] = mapped_column(String(50), default=DEFAULT_LLM_PROTOCOL)
    model: Mapped[str] = mapped_column(String(100), default="")
    max_tokens: Mapped[int] = mapped_column(Integer, default=DEFAULT_MAX_OUTPUT_TOKENS)
    context_window: Mapped[int] = mapped_column(Integer, default=DEFAULT_CONTEXT_WINDOW)
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_audio_input: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_audio_output: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_video_input: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_handler: Mapped[str] = mapped_column(String(100), default="")
    fallback_mode: Mapped[str] = mapped_column(String(30), default="")
    extras: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class LlmProvider(ApiBase):
    """BYOK provider: API credentials and protocol ownership level, model entries inherit their credentials."""

    __tablename__ = "llm_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    api_base: Mapped[str] = mapped_column(String(500), default="")
    protocol: Mapped[str] = mapped_column(String(50), default=DEFAULT_LLM_PROTOCOL)
    api_key: Mapped[str] = mapped_column(String(500), default="")  # enc: AES-GCM
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class ModelProfile(ApiBase):
    """Model entry: capability-based declarations.

    An entry neutrally declares what it can do through capability flags (chat/vision/audio input/audio output/
    reasoning effort). It can be reused by bindings for multiple tasks, avoiding duplicate entries for the same model by purpose.
    """

    __tablename__ = "model_profiles"
    __table_args__ = (
        UniqueConstraint("provider_id", "model", name="uq_model_profiles_provider_model"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    context_window: Mapped[int] = mapped_column(Integer, default=DEFAULT_CONTEXT_WINDOW)
    max_output: Mapped[int] = mapped_column(Integer, default=DEFAULT_MAX_OUTPUT_TOKENS)
    # Neutral ability position
    cap_chat: Mapped[bool] = mapped_column(Boolean, default=False)
    cap_vision: Mapped[bool] = mapped_column(Boolean, default=False)
    cap_audio_in: Mapped[bool] = mapped_column(Boolean, default=False)
    cap_audio_out: Mapped[bool] = mapped_column(Boolean, default=False)
    cap_reasoning: Mapped[bool] = mapped_column(Boolean, default=False)
    extras: Mapped[str] = mapped_column(Text, default="{}")  # JSON; voice credentials, etc.
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class TaskBinding(ApiBase):
    """Task binding: chat / stt / tts respective default model entries with (speech) degradation policy."""

    __tablename__ = "task_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    profile_id: Mapped[int] = mapped_column(Integer, nullable=False)
    fallback_handler: Mapped[str] = mapped_column(String(100), default="")
    fallback_mode: Mapped[str] = mapped_column(String(30), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class IntegrationCredential(ApiBase):
    """Third-party integration secrets (GitHub PAT today, keyed for future integrations).

    Exactly one row per integration ``key``; the secret is AES-GCM encrypted
    (``enc:...``) and never returned in clear — list payloads only expose a
    tail mask. Auto-created by ``ApiBase.metadata.create_all`` like the rest.
    """

    __tablename__ = "integration_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    secret_enc: Mapped[str] = mapped_column(String(2000), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class LLMSettings(ApiBase):
    """Legacy single-row wide table for LLM configuration.

    Used only as the data source for the first ``pipeline_legacy`` upgrade (splitting the legacy single row into three-stage
    stage_configs); runtime uses model_profiles/task_bindings, stage_configs only legacy fallback. Do not add new consumers.
    """

    __tablename__ = "llm_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    api_base: Mapped[str] = mapped_column(String(500), default="")
    api_key: Mapped[str] = mapped_column(String(500), default="")
    model: Mapped[str] = mapped_column(String(100), default="")
    max_tokens: Mapped[int] = mapped_column(Integer, default=DEFAULT_MAX_OUTPUT_TOKENS)
    context_window: Mapped[int] = mapped_column(Integer, default=DEFAULT_CONTEXT_WINDOW)
    provider: Mapped[str] = mapped_column(String(50), default="")
    protocol: Mapped[str] = mapped_column(String(50), default=DEFAULT_LLM_PROTOCOL)
    reasoning_effort: Mapped[str] = mapped_column(String(20), default="medium")
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_audio: Mapped[bool] = mapped_column(Boolean, default=False)
    # Compatible with old fields: Recognition model/Edge timbre
    stt_model: Mapped[str] = mapped_column(String(50), default="whisper-1")
    tts_voice: Mapped[str] = mapped_column(String(100), default="zh-CN-XiaoxiaoNeural")
    # ── Three-stage processor assignment ──────────────────────────────
    # Stage 1 Speech Recognition
    speech_recognize_handler: Mapped[str] = mapped_column(String(50), default="local")
    speech_recognize_mode: Mapped[str] = mapped_column(String(30), default="transcribe")
    asr_api_base: Mapped[str] = mapped_column(String(500), default="")
    asr_api_key: Mapped[str] = mapped_column(String(500), default="")
    asr_model: Mapped[str] = mapped_column(String(100), default="")
    asr_app_id: Mapped[str] = mapped_column(String(100), default="")
    asr_api_secret: Mapped[str] = mapped_column(String(500), default="")
    asr_access_key: Mapped[str] = mapped_column(String(500), default="")
    asr_resource_id: Mapped[str] = mapped_column(String(100), default="")
    asr_app_key: Mapped[str] = mapped_column(String(100), default="")
    # Stage 3 speech output (stage 2 reuses the above provider/api_* / model)
    speech_speak_handler: Mapped[str] = mapped_column(String(50), default="edge")
    speech_speak_mode: Mapped[str] = mapped_column(String(30), default="tts_from_text")
    tts_api_base: Mapped[str] = mapped_column(String(500), default="")
    tts_api_key: Mapped[str] = mapped_column(String(500), default="")
    tts_model: Mapped[str] = mapped_column(String(100), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


__all__ = ["IntegrationCredential", "LLMSettings", "StageConfig", "LlmProvider", "ModelProfile", "TaskBinding"]
