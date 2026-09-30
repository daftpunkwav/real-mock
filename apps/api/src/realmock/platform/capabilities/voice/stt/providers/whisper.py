"""Whisper STT service (faster-whisper)."""

import base64
import io
import logging
import time
import wave

logger = logging.getLogger(__name__)

# Mixing Chinese and English is common in technical interviews, helping models retain English terminology
_BILINGUAL_PROMPT = (
    "The following is a technical interview conversation in Chinese and English, which may include API, Python, JavaScript, React,"
    "English technical terms such as Agent, GitHub, Docker, Kubernetes, SQL, HTTP, and REST."
)

# Model cache policy: successes live for the process lifetime; a failed load
# (first use downloads weights from HuggingFace) is remembered so subsequent
# calls fail fast instead of re-hanging every utterance on a fresh download
# attempt, but is retried after _RETRY_AFTER_SECONDS so transient network
# failures recover without a restart. The reason is kept for
# local_stt_unavailable_reason() so callers can surface it to the user.
_MODELS: dict[str, object] = {}
_FAILURES: dict[str, tuple[float, str]] = {}
_RETRY_AFTER_SECONDS = 300.0


def _get_model(model_size: str = "base"):
    cached = _MODELS.get(model_size)
    if cached is not None:
        return cached
    now = time.monotonic()
    failed_at, _reason = _FAILURES.get(model_size, (0.0, ""))
    if now - failed_at < _RETRY_AFTER_SECONDS:
        return None
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
    except Exception as e:
        _FAILURES[model_size] = (now, str(e))
        logger.error(
            "Local STT model %r failed to load (first use downloads weights from "
            "HuggingFace); local recognition is unavailable, retry in %ss: %s",
            model_size,
            _RETRY_AFTER_SECONDS,
            e,
        )
        return None
    _FAILURES.pop(model_size, None)
    _MODELS[model_size] = model
    return model


def local_stt_unavailable_reason(model_size: str | None = None) -> str | None:
    """Most recent local model load failure, or ``None`` when recognition works.

    ``model_size`` filters to one size; ``None`` considers any failed size (the
    weight download path is shared, so one failure usually explains all sizes).
    """
    if model_size is not None and model_size in _MODELS:
        return None
    if not _FAILURES:
        return None
    _, reason = max(_FAILURES.items(), key=lambda kv: kv[1][0])[1]
    return reason


def reset_model_cache() -> None:
    """Test hook: clear cached models and remembered load failures."""
    _MODELS.clear()
    _FAILURES.clear()


def pcm_base64_to_wav_bytes(pcm_b64: str, sample_rate: int = 16000) -> bytes:
    """Convert base64 PCM Int16 to WAV bytes."""
    pcm = base64.b64decode(pcm_b64)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def transcribe_pcm_base64(pcm_b64: str, sample_rate: int = 16000, model_size: str = "base") -> str:
    """Transcribe PCM audio, and return an empty string if it fails or is judged to be no voice. Automatically detect Chinese/English."""
    model = _get_model(model_size)
    if model is None:
        return ""

    try:
        # If the audio is too short, skip it directly to avoid noise illusion.
        raw = base64.b64decode(pcm_b64)
        if len(raw) < sample_rate * 2 * 0.35:  # < ~0.35s for int16 mono
            return ""
        wav_bytes = pcm_base64_to_wav_bytes(pcm_b64, sample_rate)
        # language=None: automatic detection to avoid forcing zh to listen to English as garbled characters
        segments, info = model.transcribe(
            io.BytesIO(wav_bytes),
            language=None,
            beam_size=2,
            vad_filter=True,
            no_speech_threshold=0.6,
            initial_prompt=_BILINGUAL_PROMPT,
        )
        try:
            lang_prob = getattr(info, "language_probability", None)
            # Discard the automatic language when the confidence level is too low; do not use "does it look like Chinese" to accidentally kill English?
            if lang_prob is not None and lang_prob < 0.25:
                return ""
        except Exception:
            logger.debug("Failed to read language confidence, skip low confidence filtering", exc_info=True)
        text = "".join(seg.text for seg in segments).strip()
        # Very short-term results are mostly hallucinations
        if len(text) < 2:
            return ""
        return text
    except Exception as e:
        logger.error("Whisper transcription failed: %s", e)
        return ""


async def warmup_whisper(model_size: str = "base") -> None:
    """Preheat the model in the background to reduce the first response delay."""
    import asyncio

    def _load() -> None:
        _get_model(model_size)

    try:
        await asyncio.to_thread(_load)
    except Exception as e:
        logger.warning("Whisper warm-up failed: %s", e)


async def transcribe_pcm_base64_async(
    pcm_b64: str, sample_rate: int = 16000, model_size: str = "base"
) -> str:
    import asyncio
    return await asyncio.to_thread(transcribe_pcm_base64, pcm_b64, sample_rate, model_size)
