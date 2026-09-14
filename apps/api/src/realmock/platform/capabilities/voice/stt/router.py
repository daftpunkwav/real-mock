"""STT supplier routing: distributed by handler id, failure to fall back to local Whisper."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from realmock.platform.capabilities.voice.stt.aliyun import AliyunProvider
from realmock.platform.capabilities.voice.stt.baidu import BaiduProvider
from realmock.platform.capabilities.voice.stt.base import SttCredentials, SttProvider
from realmock.platform.capabilities.voice.stt.local import LocalWhisperProvider
from realmock.platform.capabilities.voice.stt.openai_compat import MimoAudioProvider, OpenAICompatProvider
from realmock.platform.capabilities.voice.stt.tencent import TencentProvider
from realmock.platform.capabilities.voice.stt.volcengine import VolcengineProvider
from realmock.platform.capabilities.voice.stt.xfyun import XfyunProvider
from realmock.platform.capabilities.voice.config.catalog import find_provider

logger = logging.getLogger(__name__)

_PROVIDERS: dict[str, SttProvider] = {
    "openai_compat": OpenAICompatProvider(),
    "mimo_audio": MimoAudioProvider(),
    "local": LocalWhisperProvider(),
    "xfyun": XfyunProvider(),
    "volcengine": VolcengineProvider(),
    "aliyun": AliyunProvider(),
    "tencent": TencentProvider(),
    "baidu": BaiduProvider(),
}


@dataclass(frozen=True)
class SttResult:
    """Transcription result; ``fallback=True`` indicates that the user-configured main provider is not used."""

    text: str
    provider: str
    fallback: bool = False
    requested_provider: str | None = None


async def transcribe_with_handler(
    pcm_b64: str,
    *,
    sample_rate: int,
    creds: SttCredentials,
    fallback_local: bool = True,
) -> SttResult:
    """Translated by ``creds.provider``; coming_soon/unknown provider fallback local."""
    if not pcm_b64:
        return SttResult(text="", provider="local")

    requested = (creds.provider or "local").strip()
    provider_id = requested
    meta = find_provider("recognize", provider_id)
    forced_fallback = False
    if meta and meta.get("status") == "coming_soon":
        logger.info("Identification processor %s has not been connected yet, fall back to local Whisper", provider_id)
        provider_id = "local"
        forced_fallback = True

    if meta and meta.get("recognize_via") == "native_audio" and meta.get("status") != "ready":
        logger.info("native_audio recognizes that it is not connected and falls back to local")
        provider_id = "local"
        forced_fallback = True

    impl = _PROVIDERS.get(provider_id)
    # There is no fixed handler id for custom suppliers; audio models in OpenAI Chat format are unified
    # input_audio adapter (MiMo ASR is this protocol).
    if impl is None and creds.protocol == "openai_chat":
        impl = _PROVIDERS["mimo_audio"]
        provider_id = requested
    if impl is None:
        logger.warning("Unknown recognition handler %s, fallback to local", provider_id)
        impl = _PROVIDERS["local"]
        provider_id = "local"
        forced_fallback = True

    text = ""
    try:
        text = await impl.transcribe(pcm_b64, sample_rate=sample_rate, creds=creds)
    except Exception as e:
        logger.error("ASR provider=%s Exception: %s", provider_id, e)

    if text:
        return SttResult(
            text=text,
            provider=provider_id,
            fallback=forced_fallback or provider_id != requested,
            requested_provider=requested,
        )

    fallback_handler = (creds.fallback_handler or "local").strip()
    if creds.fallback_mode in ("none", "text_only"):
        return SttResult(
            text="",
            provider=provider_id,
            fallback=True,
            requested_provider=requested,
        )
    if (
        fallback_local
        and fallback_handler not in ("", "none", "text_only")
        and fallback_handler != requested
    ):
        fallback_impl = _PROVIDERS.get(fallback_handler)
        if fallback_impl is not None:
            logger.info("ASR provider=%s No result, fallback to %s", provider_id, fallback_handler)
            fallback_creds = replace(
                creds,
                provider=fallback_handler,
                protocol="openai_chat" if fallback_handler == "local" else creds.protocol,
                model="base" if fallback_handler == "local" else creds.model,
            )
            try:
                fallback_text = await fallback_impl.transcribe(
                    pcm_b64,
                    sample_rate=sample_rate,
                    creds=fallback_creds,
                )
            except Exception as fe:
                # The primary provider has failed, and downgrade path exceptions are not thrown upward (consistent with primary path fault tolerance semantics)
                logger.error("ASR fallback provider=%s Exception: %s", fallback_handler, fe)
                fallback_text = ""
            return SttResult(
                text=fallback_text,
                provider=fallback_handler,
                fallback=True,
                requested_provider=requested,
            )
    if fallback_local and fallback_handler not in ("", "none", "text_only") and provider_id != "local":
        logger.info("ASR provider=%s The configured downgrade handler %s is not available", provider_id, fallback_handler)
        return SttResult(
            text="",
            provider=provider_id,
            fallback=True,
            requested_provider=requested,
        )
    return SttResult(
        text="",
        provider=provider_id,
        fallback=forced_fallback,
        requested_provider=requested,
    )
