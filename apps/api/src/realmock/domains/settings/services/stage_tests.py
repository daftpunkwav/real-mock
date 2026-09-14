"""Three-stage connectivity tests (recognize / reason / speak)."""

from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path

from sqlalchemy.orm import Session

from realmock.platform.capabilities.ai.llm.unified_client import UnifiedLLMClient
from realmock.platform.capabilities.voice.stt import transcribe_utterance_result
from realmock.platform.capabilities.voice.stt.base import SttCredentials
from realmock.platform.capabilities.voice.tts import TtsCredentials, synthesize_custom_speech, synthesize_speech
from realmock.platform.capabilities.voice.config.catalog import find_provider
from realmock.platform.services.pipeline.config import get_stage_config_for_runtime

logger = logging.getLogger(__name__)

# parents[3]: this file lives under domains/settings/services/ → realmock/ root
_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "platform" / "data" / "stt_fixtures"
_EXPECTED_PATH = _FIXTURE_DIR / "expected.json"
_AUDIO_PATH = _FIXTURE_DIR / "audio_zh_growth.wav"


def _normalize_zh(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"[\s\W_]+", "", t, flags=re.UNICODE)
    return t


def load_fixture() -> tuple[bytes, str]:
    # Built-in default expected text is English; used only as fallback when fixture file is missing/unreadable.
    expected = "An increase of 50% year-on-year"
    if _EXPECTED_PATH.is_file():
        try:
            data = json.loads(_EXPECTED_PATH.read_text(encoding="utf-8"))
            expected = str(data.get("expected_zh") or expected)
        except Exception:
            logger.debug("Failed to read STT fixture expected text; using built-in default", exc_info=True)
    if not _AUDIO_PATH.is_file():
        raise FileNotFoundError(f"Missing standard test audio: {_AUDIO_PATH}")
    return _AUDIO_PATH.read_bytes(), expected


async def test_recognize(db: Session, *, profile_id: int | None = None) -> dict:
    cfg = get_stage_config_for_runtime(db, "recognize", profile_id=profile_id)
    provider = cfg.get("provider") or (
        "custom" if cfg.get("api_base") and cfg.get("api_key") else "local"
    )
    meta = find_provider("recognize", provider)
    if meta and meta.get("status") == "coming_soon":
        fallback = cfg.get("fallback_handler") or "local"
        return {
            "success": False,
            "message": (
                f"Recognition processor {provider} is not wired at runtime; "
                "use a transcription ASR or local Whisper"
            ),
            "fallback": fallback,
        }

    try:
        wav_bytes, expected = load_fixture()
    except FileNotFoundError as e:
        return {"success": False, "message": str(e)}

    # Mimo audio path expects full wav base64; older openai_compat adapters convert internally
    audio_b64 = base64.b64encode(wav_bytes).decode("ascii")

    extras = cfg.get("extras") or {}
    creds = SttCredentials(
        provider=provider,
        protocol=cfg.get("protocol") or "openai_chat",
        api_base=cfg.get("api_base") or "",
        api_key=cfg.get("api_key") or "",
        model=cfg.get("model") or "",
        app_id=extras.get("asr_app_id") or "",
        api_secret=extras.get("asr_api_secret") or "",
        access_key=extras.get("asr_access_key") or "",
        resource_id=extras.get("asr_resource_id") or "",
        app_key=extras.get("asr_app_key") or "",
        fallback_handler=cfg.get("fallback_handler") or "local",
        fallback_mode=cfg.get("fallback_mode") or "transcribe",
    )

    transcription = await transcribe_utterance_result(
        audio_b64, sample_rate=16000, creds=creds, prefer_cloud=True
    )
    text = transcription.text
    if transcription.fallback:
        return {
            "success": False,
            "message": (
                f"Primary recognizer returned no result; fell back to {transcription.provider}. "
                "Check configuration."
            ),
            "transcript": text or None,
            "model": cfg.get("model") or provider,
            "fallback": transcription.provider,
        }
    norm_got = _normalize_zh(text)
    norm_exp = _normalize_zh(expected)
    ok = bool(text) and (norm_exp in norm_got or norm_got in norm_exp)
    return {
        "success": ok,
        "message": (
            f"Transcription matched: {text}"
            if ok
            else f"Transcription did not match expected '{expected}', got '{text or '(empty)'}'"
        ),
        "transcript": text or None,
        "model": cfg.get("model") or provider,
    }


async def test_reason(db: Session, *, profile_id: int | None = None) -> dict:
    cfg = get_stage_config_for_runtime(db, "reason", profile_id=profile_id)
    provider = cfg.get("provider") or ""

    meta = find_provider("reasoning", provider)
    if meta and meta.get("status") == "coming_soon":
        fallback = cfg.get("fallback_handler") or ""
        return {
            "success": False,
            "message": f"Reasoning processor {provider} is marked not wired; pick another text LLM",
            "fallback": fallback,
        }

    api_key = cfg.get("api_key") or ""
    if not api_key or not cfg.get("api_base") or not cfg.get("model"):
        return {"success": False, "message": "Configure the interview reasoning processor API Key first"}

    llm = UnifiedLLMClient.from_stage_config(cfg)
    try:
        success, message = await llm.test_connection()
        if success:
            reply = await llm.chat(
                [{"role": "user", "content": "In one sentence, introduce yourself as an interviewer."}],
                system="You are an interviewer.",
                temperature=0.7,
            )
            text = (reply or "").strip()
            if not text:
                return {"success": True, "message": message or "Connection OK", "model": llm.model}
            return {
                "success": True,
                "message": f"Reasoning OK: {text[:120]}",
                "model": llm.model,
                "transcript": text[:500],
            }
        return {"success": False, "message": message, "model": llm.model}
    except Exception as e:
        return {"success": False, "message": f"Reasoning test failed: {e}"}


async def test_speak(db: Session, *, profile_id: int | None = None) -> dict:
    cfg = get_stage_config_for_runtime(db, "speak", profile_id=profile_id)
    provider = cfg.get("provider") or (
        "custom" if cfg.get("api_base") and cfg.get("api_key") else "edge"
    )
    extras = cfg.get("extras") or {}
    mode = extras.get("speech_speak_mode") or "tts_from_text"
    meta = find_provider("speak", provider)
    if meta and meta.get("status") == "coming_soon":
        fallback = cfg.get("fallback_handler") or "edge"
        return {
            "success": False,
            "message": f"Speech processor {provider} is not wired at runtime; will fall back to Edge TTS",
            "fallback": fallback,
        }
    if mode == "text_only" or provider == "none":
        return {"success": True, "message": "Configured as captions-only; no audio synthesis needed"}

    creds = TtsCredentials(
        handler=provider,
        mode=mode,
        protocol=cfg.get("protocol") or "openai_chat",
        api_base=cfg.get("api_base") or "",
        api_key=cfg.get("api_key") or "",
        model=cfg.get("model") or "",
        voice=extras.get("tts_voice")
        or ("zh-CN-XiaoxiaoNeural" if provider == "edge" else "mimo_default"),
        fallback_handler=cfg.get("fallback_handler") or "edge",
        fallback_mode=cfg.get("fallback_mode") or "tts_from_text",
    )
    sample = "Hello, I am the interviewer."
    if provider not in ("edge", "minimax_speech", "none"):
        audio = await synthesize_custom_speech(sample, creds=creds)
    else:
        audio = await synthesize_speech(sample, creds=creds)
    if audio:
        return {
            "success": True,
            "message": f"Speech synthesis OK (handler={provider})",
            "audio_base64": audio,
            "model": cfg.get("model") or provider,
        }
    return {
        "success": False,
        "message": (
            f"Speech processor failed (handler={provider}); no fallback preview was run. "
            "Check network or credentials."
        ),
        "fallback": cfg.get("fallback_handler") or "edge",
    }
