"""LLM/processor three-phase configuration contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from realmock.platform.core.constants import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_MAX_OUTPUT_TOKENS,
)


# Single model capability switch.
class StageModelCapability(BaseModel):

    supports_vision: bool = False
    supports_audio_input: bool = False
    supports_audio_output: bool = False
    supports_video_input: bool = False


# Staged downgrade handling configuration.
class StageFallbackConfig(BaseModel):

    handler: str = ""
    mode: str = ""


# A single stage handler saves the request.
class StageConfigUpdate(BaseModel):

    provider: str = ""
    api_base: str = ""
    api_key: str = ""
    protocol: Literal["openai_chat", "anthropic_messages", "openai_responses"] = "openai_chat"
    model: str = ""
    max_tokens: int = Field(default=DEFAULT_MAX_OUTPUT_TOKENS, ge=1)
    context_window: int = Field(default=DEFAULT_CONTEXT_WINDOW, ge=1)
    capabilities: StageModelCapability = Field(default_factory=StageModelCapability)
    fallback: StageFallbackConfig = Field(default_factory=StageFallbackConfig)
    extras: dict[str, Any] = Field(default_factory=dict)


# Single stage handler returns.
class StageConfigResponse(BaseModel):

    stage: str
    provider: str
    api_base: str
    protocol: str
    model: str
    max_tokens: int
    context_window: int
    capabilities: StageModelCapability
    fallback: StageFallbackConfig
    extras: dict[str, Any]
    has_api_key: bool
    updated_at: datetime | None = None


# The new version of the three-stage configuration returns.
class StageConfigsResponse(BaseModel):

    recognize: StageConfigResponse
    reason: StageConfigResponse
    speak: StageConfigResponse
    updated_at: datetime | None = None


class LLMTestResponse(BaseModel):
    success: bool
    message: str
    model: str | None = None
    transcript: str | None = None
    audio_base64: str | None = None
    fallback: str | None = None
    latency_ms: int | None = None


# Optional override; default configuration is saved in the library.
class StageTestRequest(BaseModel):

    stage: Literal["recognize", "reason", "speak"] | None = None
