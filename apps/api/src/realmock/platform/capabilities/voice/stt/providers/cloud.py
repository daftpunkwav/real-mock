"""OpenAI-compatible cloud speech transcription (/v1/audio/transcriptions).

Uses **dedicated ASR credentials** for OpenAI, Groq, SiliconFlow, and others;
never silently reuse the key for the interview reasoning LLM (such as MiniMax Coding Plan).
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from realmock.platform.config import get_settings
from realmock.platform.core.security import make_pinned_async_client, redact_api_key
from realmock.platform.capabilities.voice.stt.providers.whisper import pcm_base64_to_wav_bytes

logger = logging.getLogger(__name__)

# Tips for speaking in Chinese and English during technical interviews to help retain proper nouns
_BILINGUAL_PROMPT = (
    "The following is a technical interview conversation in Chinese and English. May include: interviewer, candidate, self-introduction,"
    "API, Python, JavaScript, React, Agent, GitHub, Docker, Kubernetes, "
    "SQL, HTTP, REST, ByteDance, algorithms, project experience and other vocabulary."
)

# Local faster-whisper size name; the rest are treated as cloud model ids
LOCAL_WHISPER_SIZES = frozenset(
    {
        "tiny",
        "base",
        "small",
        "medium",
        "large",
        "large-v1",
        "large-v2",
        "large-v3",
        "distil-large-v3",
        "distil-small.en",
    }
)


def is_local_stt_model(model: str) -> bool:
    return (model or "").strip().lower() in LOCAL_WHISPER_SIZES


def resolve_cloud_stt_model(model: str) -> str:
    """Fallback to generic cloud model whisper-1 when using local size names."""
    m = (model or "").strip()
    if not m or is_local_stt_model(m):
        return "whisper-1"
    return m


async def transcribe_pcm_cloud(
    pcm_b64: str,
    *,
    sample_rate: int = 16000,
    model: str = "whisper-1",
    api_base: str = "",
    api_key: str = "",
    language: str | None = None,
    full_url: bool = False,
) -> str:
    """Calls OpenAI compatible transcriptions; returns an empty string on failure."""
    key = (api_key or "").strip()
    base = (api_base or "").rstrip("/")
    if not key or not base:
        return ""

    raw_len = 0
    try:
        import base64

        raw_len = len(base64.b64decode(pcm_b64))
    except Exception:
        return ""
    # < ~0.35s int16 mono
    if raw_len < sample_rate * 2 * 0.35:
        return ""

    try:
        wav_bytes = pcm_base64_to_wav_bytes(pcm_b64, sample_rate)
    except Exception as e:
        logger.warning("PCM→WAV failed: %s", e)
        return ""

    # Full-URL mode posts to api_base verbatim; otherwise the documented path is appended.
    url = base if full_url else f"{base}/audio/transcriptions"
    cloud_model = resolve_cloud_stt_model(model)
    settings = get_settings()
    data: dict[str, str] = {
        "model": cloud_model,
        "response_format": "json",
        "prompt": _BILINGUAL_PROMPT,
    }
    # The interview is mainly in Chinese; if it is not mandatory, some suppliers will automatically detect it better. The default here is zh to improve the accuracy of Chinese.
    if language:
        data["language"] = language
    else:
        data["language"] = "zh"

    files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
    headers = {"Authorization": f"Bearer {key}"}

    try:
        # Keep DNS resolution off the event loop (same convention as web_fetch).
        pinned = await asyncio.to_thread(
            make_pinned_async_client,
            url,
            allow_local=settings.allow_local_llm,
            require_https=bool(settings.is_prod),
            timeout=25.0,
        )
        async with pinned as client:
            resp = await client.post(url, headers=headers, data=data, files=files)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as e:
        body = ""
        try:
            body = (e.response.text or "")[:200]
        except Exception:
            logger.debug("Failed to read STT error response body", exc_info=True)
        logger.error(
            "Cloud STT HTTP %s key=%s: %s",
            e.response.status_code,
            redact_api_key(key),
            body,
        )
        return ""
    except Exception as e:
        logger.error("Cloud STT failed key=%s: %s", redact_api_key(key), e)
        return ""

    text = ""
    if isinstance(payload, dict):
        text = str(payload.get("text") or "").strip()
    elif isinstance(payload, str):
        text = payload.strip()
    if len(text) < 2:
        return ""
    return text
