"""OpenAI-compatible / Mimo audio transcription adapter (uses chat.completions to support mimo-v2.5-asr)."""

from __future__ import annotations

import base64
import logging

import httpx

from realmock.platform.config import get_settings
from realmock.platform.core.security import make_pinned_async_client, redact_api_key
from realmock.platform.capabilities.voice.stt.base import SttCredentials

logger = logging.getLogger(__name__)


class MimoAudioProvider:
    """Call OpenAI Chat and pass the audio to the ASR model as input_audio."""

    async def transcribe(
        self, pcm_b64: str, *, sample_rate: int, creds: SttCredentials
    ) -> str:
        api_key = (creds.api_key or "").strip()
        api_base = (creds.api_base or "").rstrip("/")
        model = creds.model or "mimo-v2.5-asr"
        if not api_key or not api_base:
            return ""

        # The router passes in the base64 of wav (or pcm); it is prioritized as wav with RIFF header.
        wav_bytes = _decode_audio(pcm_b64)
        if not wav_bytes:
            return ""
        audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
        data_uri = f"data:audio/wav;base64,{audio_b64}"

        # Full-URL mode posts to api_base verbatim; otherwise the documented path is appended.
        url = api_base if creds.full_url else f"{api_base}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_audio", "input_audio": {"data": data_uri}}
                    ],
                }
            ],
            "asr_options": {"language": "zh"},
        }
        headers = {"api-key": api_key, "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        settings = get_settings()
        try:
            async with make_pinned_async_client(
                api_base,
                allow_local=settings.allow_local_llm,
                require_https=bool(settings.is_prod),
                timeout=30.0,
            ) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                "MimoAudio ASR HTTP %s key=%s: %s",
                e.response.status_code,
                redact_api_key(api_key),
                e.response.text[:200],
            )
            return ""
        except Exception as e:
            logger.error("MimoAudio ASR failed key=%s: %s", redact_api_key(api_key), e)
            return ""

        msg = data.get("choices", [{}])[0].get("message", {}) if data.get("choices") else {}
        text = ""
        content = msg.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return text.strip()


def _decode_audio(pcm_b64: str) -> bytes:
    try:
        raw = base64.b64decode(pcm_b64)
        if raw[:4] == b"RIFF":
            return raw
        from realmock.platform.capabilities.voice.stt.providers.cloud import pcm_base64_to_wav_bytes

        # Fixed 16k encapsulation; ignore incoming sample_rate.
        return pcm_base64_to_wav_bytes(pcm_b64, 16000)
    except Exception:
        return b""


async def transcribe_pcm_cloud(
    pcm_b64: str,
    *,
    sample_rate: int = 16000,
    model: str = "whisper-1",
    api_base: str = "",
    api_key: str = "",
    full_url: bool = False,
) -> str:
    """Transcribe via the OpenAI-compatible /audio/transcriptions endpoint (legacy function retained for test compatibility)."""
    from realmock.platform.capabilities.voice.stt.providers.cloud import transcribe_pcm_cloud as _cloud

    return await _cloud(
        pcm_b64,
        sample_rate=sample_rate,
        model=model,
        api_base=api_base,
        api_key=api_key,
        full_url=full_url,
    )


class OpenAICompatProvider:
    async def transcribe(
        self, pcm_b64: str, *, sample_rate: int, creds: SttCredentials
    ) -> str:
        return await transcribe_pcm_cloud(
            pcm_b64,
            sample_rate=sample_rate,
            model=creds.model or "FunAudioLLM/SenseVoiceSmall",
            api_base=creds.api_base,
            api_key=creds.api_key,
            full_url=creds.full_url,
        )
