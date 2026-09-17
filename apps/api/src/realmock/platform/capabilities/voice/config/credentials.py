"""Build STT/TTS runtime credentials from a resolved stage-config mapping.

Callers fetch the mapping via
:func:`realmock.platform.services.pipeline.config.get_stage_config_for_runtime`
so this module stays a pure transformer (no services-layer dependency).
"""

from __future__ import annotations

from typing import Any, Mapping

from realmock.platform.capabilities.voice.stt.base import SttCredentials
from realmock.platform.capabilities.voice.tts import TtsCredentials


def build_stt_credentials(cfg: Mapping[str, Any]) -> SttCredentials:
    """Build independent identification credentials; never fall back on thinking about Key.

    The handler id prefers the channel's ``vendor`` (catalog vendor id, e.g. ``minimax``);
    the provider display name is only a legacy fallback from before channels existed.
    """
    extras = cfg.get("extras") or {}
    provider = (
        cfg.get("vendor")
        or cfg.get("provider")
        or ("custom" if cfg.get("api_base") and cfg.get("api_key") else "local")
    )
    return SttCredentials(
        provider=provider,
        protocol=cfg.get("protocol") or "openai_chat",
        api_base=cfg.get("api_base") or "",
        full_url=bool(cfg.get("full_url")),
        api_key=cfg.get("api_key") or "",
        model=cfg.get("model") or "base",
        app_id=extras.get("asr_app_id") or "",
        api_secret=extras.get("asr_api_secret") or "",
        access_key=extras.get("asr_access_key") or "",
        resource_id=extras.get("asr_resource_id") or "",
        app_key=extras.get("asr_app_key") or "",
        fallback_handler=cfg.get("fallback_handler") or "local",
        fallback_mode=cfg.get("fallback_mode") or "transcribe",
        # User-authored request overrides/adapters (stt_request / stt_adapter) for the adapters.
        extra=dict(extras),
    )


def build_tts_credentials(cfg: Mapping[str, Any]) -> TtsCredentials:
    """Build independent broadcast credentials; handler id prefers the channel ``vendor``."""
    extras = cfg.get("extras") or {}
    handler = (
        cfg.get("vendor")
        or cfg.get("provider")
        or ("custom" if cfg.get("api_base") and cfg.get("api_key") else "edge")
    )
    return TtsCredentials(
        handler=handler,
        mode=extras.get("speech_speak_mode") or "tts_from_text",
        protocol=cfg.get("protocol") or "openai_chat",
        api_base=cfg.get("api_base") or "",
        full_url=bool(cfg.get("full_url")),
        api_key=cfg.get("api_key") or "",
        model=cfg.get("model") or "",
        voice=extras.get("tts_voice")
        or ("zh-CN-XiaoxiaoNeural" if handler == "edge" else "mimo_default"),
        fallback_handler=cfg.get("fallback_handler") or "edge",
        fallback_mode=cfg.get("fallback_mode") or "tts_from_text",
        # User-authored request overrides/adapters (tts_request / tts_adapter) for the adapters.
        extra=dict(extras),
    )
