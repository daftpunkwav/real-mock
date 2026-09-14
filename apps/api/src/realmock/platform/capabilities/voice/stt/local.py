"""Local faster-whisper adapter."""

from __future__ import annotations

from realmock.platform.capabilities.voice.stt.base import SttCredentials
from realmock.platform.capabilities.voice.stt.cloud import is_local_stt_model
from realmock.platform.capabilities.voice.stt.whisper import transcribe_pcm_base64_async


class LocalWhisperProvider:
    async def transcribe(
        self, pcm_b64: str, *, sample_rate: int, creds: SttCredentials
    ) -> str:
        model = creds.model if is_local_stt_model(creds.model) else "small"
        return await transcribe_pcm_base64_async(
            pcm_b64, sample_rate=sample_rate, model_size=model
        )
