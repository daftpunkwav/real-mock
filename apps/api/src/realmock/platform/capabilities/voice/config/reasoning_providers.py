"""Phase 2 Think about the processor catalog."""

from __future__ import annotations

from typing import Any

from .catalog_schema import _p

# Thinking Processor (Phase 2)
REASONING_PROVIDERS: list[dict[str, Any]] = [
    _p(
        id="custom",
        label="custom supplier",
        can_interview_reason=True,
        default_model="",
        default_api_base="",
        hint="Fill in the Base URL, API format, API Key and model name",
    ),
    _p(
        id="minimax",
        label="MiniMax (Text Thinking)",
        can_interview_reason=True,
        default_model="MiniMax-M3",
        default_api_base="https://api.minimaxi.com/v1",
        hint="Text LLM; not responsible for listening/speaking",
        vendor="minimax",
    ),
    _p(
        id="openai",
        label="OpenAI",
        can_interview_reason=True,
        default_model="gpt-4o",
        default_api_base="https://api.openai.com/v1",
        vendor="openai",
    ),
    _p(
        id="deepseek",
        label="DeepSeek",
        can_interview_reason=True,
        default_model="deepseek-chat",
        default_api_base="https://api.deepseek.com/v1",
        vendor="deepseek",
    ),
    _p(
        id="stepfun",
        label="StepFun",
        can_interview_reason=True,
        default_api_base="https://api.stepfun.com/step_plan/v1",
        vendor="stepfun",
    ),
    _p(
        id="openrouter",
        label="OpenRouter",
        can_interview_reason=True,
        default_api_base="https://openrouter.ai/api/v1",
        vendor="openrouter",
    ),
    _p(
        id="mimo",
        label="Xiaomi MiMo",
        can_interview_reason=True,
        can_speech_recognize=True,
        can_speech_speak=True,
        recognize_via="transcribe_only",
        speak_via="tts_from_text",
        default_model="mimo-v2.5",
        default_api_base="https://token-plan-cn.xiaomimimo.com/v1",
        hint="Text model: mimo-v2.5; configure mimo-v2.5-asr/tts separately for the three speech recognition/synthesis stages",
        vendor="xiaomi",
    ),
    _p(
        id="zhipu_glm4_voice",
        label="GLM-4-Voice",
        can_speech_recognize=True,
        can_interview_reason=True,
        can_speech_speak=True,
        recognize_via="native_audio",
        speak_via="native_audio",
        status="coming_soon",
        hint="Can be heard or spoken; the current round of native conversation is not connected; the text LLM must still be selected during the thinking stage",
    ),
]
