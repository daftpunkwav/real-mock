"""Stage 3 Broadcast handler directory."""

from __future__ import annotations

from typing import Any

from .catalog_schema import _p

# Broadcast Processor (Phase 3)
SPEAK_PROVIDERS: list[dict[str, Any]] = [
    _p(
        id="custom",
        label="custom supplier",
        can_speech_speak=True,
        speak_via="tts_from_text",
        default_model="",
        default_api_base="",
        hint="Fill in the Base URL, API format, API Key and model name",
    ),
    _p(
        id="mimo_audio",
        label="Xiaomi MiMo (mimo-v2.5-tts)",
        can_speech_speak=True,
        speak_via="tts_from_text",
        default_model="mimo-v2.5-tts",
        default_api_base="https://token-plan-cn.xiaomimimo.com/v1",
        hint="OpenAI is compatible with chat.completions; specify the timbre via audio.voice",
    ),
    _p(
        id="edge",
        label="Edge TTS (Free)",
        can_speech_speak=True,
        speak_via="tts_from_text",
        default_model="zh-CN-XiaoxiaoNeural",
        hint="Current default broadcast handler",
    ),
    _p(
        id="minimax_speech",
        label="MiniMax Speech (TTS)",
        can_speech_speak=True,
        speak_via="tts_from_text",
        default_model="speech-2.8-hd",
        default_api_base="https://api.minimaxi.com/v1",
        hint="T2A text-to-speech; TTS Key can be configured separately",
    ),
    _p(
        id="none",
        label="Subtitles only (no announcement)",
        can_speech_speak=False,
        speak_via="none",
    ),
    _p(
        id="zhipu_glm4_voice",
        label="GLM-4-Voice (native voice)",
        can_speech_recognize=True,
        can_interview_reason=True,
        can_speech_speak=True,
        recognize_via="native_audio",
        speak_via="native_audio",
        status="coming_soon",
    ),
    _p(
        id="doubao_s2s",
        label="Doubao end-to-end real-time voice (native voice)",
        can_speech_recognize=True,
        can_speech_speak=True,
        recognize_via="native_audio",
        speak_via="native_audio",
        status="coming_soon",
    ),
]
