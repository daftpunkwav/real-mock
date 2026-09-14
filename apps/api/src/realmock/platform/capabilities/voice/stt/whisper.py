"""Whisper STT service (faster-whisper)."""

import base64
import io
import logging
import wave
from functools import lru_cache

logger = logging.getLogger(__name__)

# Mixing Chinese and English is common in technical interviews, helping models retain English terminology
_BILINGUAL_PROMPT = (
    "The following is a technical interview conversation in Chinese and English, which may include API, Python, JavaScript, React,"
    "English technical terms such as Agent, GitHub, Docker, Kubernetes, SQL, HTTP, and REST."
)


@lru_cache(maxsize=1)
def _get_model(model_size: str):
    try:
        from faster_whisper import WhisperModel
        return WhisperModel(model_size, device="cpu", compute_type="int8")
    except Exception as e:
        logger.warning("faster-whisper is not available: %s", e)
        return None


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
