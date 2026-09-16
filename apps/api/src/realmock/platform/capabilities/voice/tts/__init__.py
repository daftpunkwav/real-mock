"""Unified TTS entry point: supports Edge / MiniMax / OpenAI-compatible (including Mimo) / captions only."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from realmock.platform.config import get_settings
from realmock.platform.core.security import make_pinned_async_client
from realmock.platform.capabilities.voice.tts.providers.edge import synthesize_to_base64 as edge_synthesize
from realmock.platform.capabilities.voice.tts.providers.edge import DEFAULT_VOICE as EDGE_DEFAULT_VOICE
from realmock.platform.capabilities.voice.tts.providers.json_template import (
    resolve_tts_adapter,
    synthesize_json_template_to_base64,
)
from realmock.platform.capabilities.voice.tts.providers.minimax import (
    DEFAULT_BASE as MINIMAX_DEFAULT_BASE,
    DEFAULT_MODEL as MINIMAX_DEFAULT_MODEL,
    DEFAULT_VOICE as MINIMAX_DEFAULT_VOICE,
    synthesize_minimax_to_base64,
)
from realmock.platform.capabilities.voice.config.catalog import find_provider
from realmock.platform.capabilities.voice.endpoint_vendors import TTS_PATHS, match_vendor

logger = logging.getLogger(__name__)


@dataclass
class TtsCredentials:
    handler: str = "edge"
    mode: str = "tts_from_text"  # tts_from_text | native_audio | text_only
    protocol: str = "openai_chat"
    api_base: str = ""
    # Full-URL providers: api_base is the verbatim endpoint and protocol path appending is skipped.
    full_url: bool = False
    api_key: str = ""
    model: str = ""
    voice: str = "zh-CN-XiaoxiaoNeural"
    fallback_handler: str = "edge"
    fallback_mode: str = "tts_from_text"
    # User-authored request overrides/adapters (tts_request / tts_adapter) for the adapters.
    extra: dict = field(default_factory=dict)


async def synthesize_speech(
    text: str,
    *,
    creds: TtsCredentials,
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> str:
    """Synthesize speech as base64; return an empty string for text_only / coming_soon / failures (the caller continues with captions)."""
    handler = (creds.handler or "edge").strip()
    mode = (creds.mode or "tts_from_text").strip()

    if mode == "text_only" or handler == "none":
        return ""

    meta = find_provider("speak", handler)
    if meta and meta.get("status") == "coming_soon":
        logger.info("The broadcast processor %s has not yet been connected and performs the configured downgrade processing.", handler)
        return await _synthesize_fallback(text, creds, rate=rate, pitch=pitch)

    if mode == "native_audio":
        logger.info("native_audio reports that the broadcast is not connected and performs the configured downgrade processing.")
        return await _synthesize_fallback(text, creds, rate=rate, pitch=pitch)

    try:
        audio = await _synthesize_handler(text, creds, handler, rate=rate, pitch=pitch)
    except Exception as e:
        logger.error("Report handler %s Exception: %s", handler, e)
        audio = ""
    if audio:
        return audio
    logger.info("The broadcast processor %s failed and performed the configured downgrade processing.", handler)
    return await _synthesize_fallback(text, creds, rate=rate, pitch=pitch)


def _is_minimax_full_url(creds: TtsCredentials) -> bool:
    """Full-URL providers carry the vendor in the endpoint path (t2a_v2 → MiniMax)."""
    return bool(creds.full_url) and match_vendor(creds.api_base, TTS_PATHS) == "minimax"


async def _synthesize_minimax_full_url(text: str, creds: TtsCredentials) -> str:
    return await synthesize_minimax_to_base64(
        text,
        api_key=creds.api_key,
        api_base=creds.api_base,
        model=creds.model,
        voice=creds.voice,
        overrides=_minimax_overrides(creds),
    )


async def _synthesize_handler(
    text: str,
    creds: TtsCredentials,
    handler: str,
    *,
    rate: str,
    pitch: str,
) -> str:
    if handler == "none":
        return ""
    if handler == "edge":
        try:
            return await edge_synthesize(
                text, creds.voice or "zh-CN-XiaoxiaoNeural", rate=rate, pitch=pitch
            )
        except Exception as e:
            logger.error("Edge TTS failed: %s", e)
            return ""
    if handler == "minimax_speech":
        return await synthesize_minimax_to_base64(
            text,
            api_key=creds.api_key,
            api_base=creds.api_base or MINIMAX_DEFAULT_BASE,
            model=creds.model or MINIMAX_DEFAULT_MODEL,
            voice=creds.voice or MINIMAX_DEFAULT_VOICE,
            overrides=_minimax_overrides(creds),
        )
    if _is_minimax_full_url(creds):
        return await _synthesize_minimax_full_url(text, creds)
    if resolve_tts_adapter(creds) is not None:
        return await synthesize_json_template_to_base64(text, creds=creds)
    return await _synthesize_openai_compat(text, creds)


def _minimax_overrides(creds: TtsCredentials) -> dict | None:
    """User-authored request-body overrides from extras (``tts_request``)."""
    override = (creds.extra or {}).get("tts_request")
    return override if isinstance(override, dict) else None


async def _synthesize_fallback(
    text: str,
    creds: TtsCredentials,
    *,
    rate: str,
    pitch: str,
) -> str:
    fallback = (creds.fallback_handler or "edge").strip()
    if (
        not fallback
        or fallback in ("none", "text_only")
        or creds.fallback_mode == "text_only"
        or fallback == (creds.handler or "").strip()
    ):
        return ""
    fallback_creds = TtsCredentials(
        handler=fallback,
        mode=creds.fallback_mode or "tts_from_text",
        protocol=creds.protocol,
        api_base=creds.api_base,
        # Full-URL endpoints stay verbatim on the fallback path too; otherwise an
        # openai-compat fallback would re-append a path onto the complete URL.
        full_url=creds.full_url,
        api_key=creds.api_key,
        model=creds.model,
        voice=(EDGE_DEFAULT_VOICE if fallback == "edge" else creds.voice),
        fallback_handler="none",
        fallback_mode="text_only",
        extra=dict(creds.extra or {}),
    )
    return await _synthesize_handler(
        text, fallback_creds, fallback, rate=rate, pitch=pitch
    )


async def _synthesize_openai_compat(text: str, creds: TtsCredentials) -> str:
    if creds.protocol != "openai_chat":
        logger.warning("Custom TTS does not currently support API format %s", creds.protocol)
        return ""
    api_key = (creds.api_key or "").strip()
    api_base = (creds.api_base or "").rstrip("/")
    model = creds.model or "mimo-v2.5-tts"
    voice = creds.voice or "mimo_default"
    if not api_key or not api_base:
        return ""

    # Full-URL mode posts to api_base verbatim; otherwise the documented path is appended.
    url = api_base if creds.full_url else f"{api_base}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Use a natural Chinese female voice, speak at a normal speed, and broadcast smoothly."},
            {"role": "assistant", "content": text},
        ],
        "audio": {"format": "wav", "voice": voice},
    }
    headers = {"api-key": api_key, "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    settings = get_settings()
    try:
        async with make_pinned_async_client(
            api_base,
            allow_local=settings.allow_local_llm,
            require_https=bool(settings.is_prod),
            timeout=120.0,
        ) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("OpenAI compatible with TTS HTTP %s: %s", e.response.status_code, e.response.text[:200])
        return ""
    except Exception as e:
        logger.error("OpenAI compatible TTS failed: %s", e)
        return ""

    msg = data.get("choices", [{}])[0].get("message", {}) if data.get("choices") else {}
    audio = msg.get("audio")
    if isinstance(audio, dict) and audio.get("data"):
        return audio["data"]
    return ""


async def synthesize_custom_speech(text: str, *, creds: TtsCredentials) -> str:
    """Only the custom main processor is tested and Edge downgrade is not performed automatically."""
    if _is_minimax_full_url(creds):
        return await _synthesize_minimax_full_url(text, creds)
    if resolve_tts_adapter(creds) is not None:
        return await synthesize_json_template_to_base64(text, creds=creds)
    return await _synthesize_openai_compat(text, creds)


async def synthesize_primary_speech(
    text: str,
    *,
    creds: TtsCredentials,
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> str:
    """Only the anchor report processor is executed, no degradation is triggered, and it is used to set the page connectivity test."""
    handler = (creds.handler or "edge").strip()
    mode = (creds.mode or "tts_from_text").strip()
    if mode == "text_only" or handler == "none":
        return ""
    meta = find_provider("speak", handler)
    if meta and meta.get("status") == "coming_soon":
        return ""
    if mode == "native_audio":
        return ""
    try:
        return await _synthesize_handler(text, creds, handler, rate=rate, pitch=pitch)
    except Exception as e:
        logger.error("The anchor reported that the processor %s failed the test: %s", handler, e)
        return ""
