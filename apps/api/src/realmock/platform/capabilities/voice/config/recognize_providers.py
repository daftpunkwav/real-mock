"""Phase 1 Identify the processor directory."""

from __future__ import annotations

from typing import Any

from .catalog_schema import _p

# Identify the processor (Phase 1)
RECOGNIZE_PROVIDERS: list[dict[str, Any]] = [
    _p(
        id="custom",
        label="custom supplier",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        default_model="",
        default_api_base="",
        hint="Fill in the Base URL, API format, API Key and model name",
    ),
    _p(
        id="minimax",
        label="MiniMax Speech-to-Text (asr)",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        default_model="asr-1.0",
        default_api_base="https://api.minimaxi.com/v1",
        hint="Multipart wav upload; the language header is omitted by default (mixed-language recognition)",
        vendor="minimax",
    ),
    _p(
        id="mimo_audio",
        label="Xiaomi MiMo (mimo-v2.5-asr)",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        default_model="mimo-v2.5-asr",
        default_api_base="https://token-plan-cn.xiaomimimo.com/v1",
        hint="OpenAI is compatible with chat.completions; audio is passed in as input_audio",
        vendor="xiaomi",
    ),
    _p(
        id="openai_compat",
        label="OpenAI compatible transcription (SiliconFlow / Groq / OpenAI)",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        default_model="FunAudioLLM/SenseVoiceSmall",
        default_api_base="https://api.siliconflow.cn/v1",
        hint="Key needs to be transcribed independently; do not reuse and think about LLM Key",
        vendor="openai",
    ),
    _p(
        id="xfyun",
        label="iFlytek·Voice Dictation",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        hint="AppId + APIKey + APISecret",
        vendor="iflytek",
    ),
    _p(
        id="volcengine",
        label="Doubao (Volcano) · Rapid recognition of recording files",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        default_model="bigmodel",
        hint="AppKey + AccessKey; resource ID default volc.bigasr.auc_turbo",
        vendor="volcengine",
    ),
    _p(
        id="aliyun",
        label="Alibaba Cloud·Sentence Recognition",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        hint="AppKey + AccessKeyId/Secret",
        vendor="alibaba",
    ),
    _p(
        id="tencent",
        label="Tencent Cloud·Sentence Recognition",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        hint="AppId + SecretId + SecretKey",
        vendor="tencent",
    ),
    _p(
        id="baidu",
        label="Baidu·Short speech recognition",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        hint="API Key + Secret Key (for token)",
        vendor="baidu",
    ),
    _p(
        id="local",
        label="local faster-whisper",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        default_model="small",
        hint="Downgrade options without cloud key",
    ),
    _p(
        id="zhipu_glm4_voice",
        label="GLM-4-Voice (native audio listening)",
        can_speech_recognize=True,
        can_interview_reason=True,
        can_speech_speak=True,
        recognize_via="native_audio",
        speak_via="native_audio",
        status="coming_soon",
    ),
    _p(
        id="doubao_s2s",
        label="Doubao end-to-end real-time voice",
        can_speech_recognize=True,
        can_speech_speak=True,
        recognize_via="native_audio",
        speak_via="native_audio",
        status="coming_soon",
    ),
]
