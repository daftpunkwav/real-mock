"""MiniMax Speech TTS (Text → Audio)."""

from __future__ import annotations

import base64
import logging

import httpx

from realmock.platform.config import get_settings
from realmock.platform.core.security import make_pinned_async_client

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "speech-2.8-hd"
DEFAULT_VOICE = "male-qn-qingse"
DEFAULT_BASE = "https://api.minimaxi.com/v1"


async def synthesize_minimax_to_base64(
    text: str,
    *,
    api_key: str,
    api_base: str = DEFAULT_BASE,
    model: str = DEFAULT_MODEL,
    voice: str = DEFAULT_VOICE,
) -> str:
    """Call MiniMax t2a_v2; successfully returns mp3/wav base64, otherwise returns an empty string."""
    key = (api_key or "").strip()
    base = (api_base or DEFAULT_BASE).rstrip("/")
    clean = (text or "").strip()
    if not key or not clean:
        return ""

    # MiniMax documentation: POST /v1/t2a_v2
    url = f"{base}/t2a_v2"
    body = {
        "model": model or DEFAULT_MODEL,
        "text": clean,
        "stream": False,
        "voice_setting": {
            "voice_id": voice or DEFAULT_VOICE,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    settings = get_settings()
    try:
        async with make_pinned_async_client(
            url,
            allow_local=settings.allow_local_llm,
            require_https=bool(settings.is_prod),
            timeout=60.0,
        ) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as e:
        body_txt = ""
        try:
            body_txt = (e.response.text or "")[:200]
        except Exception:
            logger.debug("Failed to read TTS error response body", exc_info=True)
        logger.error("MiniMax TTS HTTP %s: %s", e.response.status_code, body_txt)
        return ""
    except Exception as e:
        logger.error("MiniMax TTS failed: %s", e)
        return ""

    data = payload.get("data") or {}
    audio = data.get("audio") or payload.get("audio") or ""
    if isinstance(audio, str) and audio:
        # Already hex or base64; MiniMax usually returns hex, fallback raw base64
        try:
            raw = bytes.fromhex(audio)
            return base64.b64encode(raw).decode("ascii")
        except ValueError:
            return audio
    logger.warning("MiniMax TTS response has no audio field keys=%s", list(payload.keys())[:8])
    return ""
