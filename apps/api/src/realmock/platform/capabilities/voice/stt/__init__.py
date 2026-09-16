"""Unified STT entrance: Routing based on independent identification credentials, prohibiting silent use of LLM Key."""

from __future__ import annotations

import logging

from realmock.platform.capabilities.voice.stt.base import SttCredentials
from realmock.platform.capabilities.voice.stt.providers.cloud import (
    LOCAL_WHISPER_SIZES,
    is_local_stt_model,
    resolve_cloud_stt_model,
)
from realmock.platform.capabilities.voice.stt.router import SttResult, transcribe_with_handler
from realmock.platform.capabilities.voice.stt.providers.whisper import (
    transcribe_pcm_base64_async as transcribe_local_async,
    warmup_whisper,
)

logger = logging.getLogger(__name__)

__all__ = [
    "LOCAL_WHISPER_SIZES",
    "SttCredentials",
    "SttResult",
    "is_local_stt_model",
    "resolve_cloud_stt_model",
    "transcribe_utterance",
    "transcribe_utterance_result",
    "warmup_whisper",
]


async def transcribe_utterance(
    pcm_b64: str,
    *,
    sample_rate: int = 16000,
    model: str = "whisper-1",
    api_base: str = "",
    api_key: str = "",
    prefer_cloud: bool = True,
    creds: SttCredentials | None = None,
) -> str:
    """DEPRECATED: Transcribe an entire user utterance and return plain text (for compatibility with legacy calls). Use transcribe_utterance_result instead."""
    result = await transcribe_utterance_result(
        pcm_b64,
        sample_rate=sample_rate,
        model=model,
        api_base=api_base,
        api_key=api_key,
        prefer_cloud=prefer_cloud,
        creds=creds,
    )
    return result.text


async def transcribe_utterance_result(
    pcm_b64: str,
    *,
    sample_rate: int = 16000,
    model: str = "whisper-1",
    api_base: str = "",
    api_key: str = "",
    prefer_cloud: bool = True,
    creds: SttCredentials | None = None,
) -> SttResult:
    """Transcribe and return results with fallback metadata."""
    if not pcm_b64:
        return SttResult(text="", provider="local")

    if creds is not None:
        return await transcribe_with_handler(
            pcm_b64,
            sample_rate=sample_rate,
            creds=creds,
            fallback_local=True,
        )

    # Compatible with old calls: only go to openai_compat when api_key/api_base is passed in explicitly
    use_cloud = prefer_cloud and bool((api_key or "").strip()) and bool((api_base or "").strip())
    if use_cloud:
        return await transcribe_with_handler(
            pcm_b64,
            sample_rate=sample_rate,
            creds=SttCredentials(
                provider="openai_compat",
                api_base=api_base,
                api_key=api_key,
                model=model,
            ),
            fallback_local=True,
        )

    local_model = model if is_local_stt_model(model) else "base"
    text = await transcribe_local_async(
        pcm_b64, sample_rate=sample_rate, model_size=local_model
    )
    return SttResult(text=text, provider="local")
