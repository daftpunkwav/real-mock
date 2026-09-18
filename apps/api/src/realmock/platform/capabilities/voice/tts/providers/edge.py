"""Speech synthesis with Edge TTS.

The edge-tts client escapes the text and wraps it in SSML itself, so injecting express-as is unsupported;
emotional realism is implemented through rate/pitch, with fallback to plain text using default prosody on failure.
"""

from __future__ import annotations

import base64
import logging
import re

logger = logging.getLogger(__name__)

# Default Chinese sounds
VOICE_PRESETS = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",
    "yunxi": "zh-CN-YunxiNeural",
    "yunyang": "zh-CN-YunyangNeural",
    "xiaoyi": "zh-CN-XiaoyiNeural",
    "yunjian": "zh-CN-YunjianNeural",
}

DEFAULT_VOICE = VOICE_PRESETS["xiaoxiao"]

# Hard segmentation point at the end of the sentence (aligned with the streaming enqueue strategy)
_HARD_END = frozenset("。！？!?；;…\n.")
# Soft segmentation of long sentences (after the word count reaches the target)
_SOFT_BREAK = frozenset("，、,")
# The soft-cut word count rotates between short/medium/long to avoid sentences that are equal in length and unrealistic.
_SOFT_MIN_ROTATION = (10, 14, 18, 24, 32)
_SOFT_MIN_CHARS = 18


def split_sentences(text: str) -> list[str]:
    """Split by Chinese and English periods for streaming TTS."""
    clean = plain_text_for_tts(text)
    parts = re.split(r"(?<=[。！？!?；;…\.\n])", clean)
    return [p.strip() for p in parts if p.strip()]


def should_flush_sentence_buffer(buf: str, soft_min: int | None = None) -> bool:
    """Whether the streaming buffer should be queued for synthesis immediately.

    - Hard sentence-ending punctuation → split
    - Length ≥ soft_min and a comma/enumeration comma is encountered → soft split (soft_min rotates at the caller to simulate alternating long and short sentences)
    - Forced split when too long: split at ≥ 48 characters even without punctuation, avoiding overly long sentences
    """
    if not buf:
        return False
    last = buf[-1]
    if last in _HARD_END:
        return True
    min_chars = soft_min if soft_min is not None else _SOFT_MIN_CHARS
    if len(buf) >= min_chars and last in _SOFT_BREAK:
        return True
    if len(buf) >= 48:
        return True
    return False


def next_soft_min(index: int) -> tuple[int, int]:
    """Return (soft_min of this round, index of next round)."""
    mins = _SOFT_MIN_ROTATION
    i = index % len(mins)
    return mins[i], index + 1


def extract_emotion(text: str) -> str:
    m = re.search(r"\[emotion:(\w+)\]", text)
    return m.group(1) if m else "neutral"


def plain_text_for_tts(text: str) -> str:
    """Remove control tags and markdown decoration to prevent TTS from pronouncing "asterisk"."""
    clean = re.sub(r"\[(PHASE_COMPLETE|INTERVIEW_COMPLETE|emotion:\w+)\]", "", text)
    # **Bold** / *Italic* → Keep text
    clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", clean)
    clean = re.sub(r"\*([^*]+)\*", r"\1", clean)
    clean = re.sub(r"__([^_]+)__", r"\1", clean)
    clean = re.sub(r"_([^_]+)_", r"\1", clean)
    clean = re.sub(r"`+", "", clean)
    clean = re.sub(r"#{1,6}\s*", "", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
    # Remaining isolated asterisk (including full-width *)
    clean = re.sub(r"[*＊]+", "", clean)
    clean = re.sub(r"[ \t]{2,}", " ", clean)
    return clean.strip()


async def _stream_communicate(communicate) -> bytes:
    audio_bytes = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes += chunk["data"]
    return audio_bytes


async def synthesize_to_base64(
    text: str,
    voice: str | None = None,
    *,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    style: str | None = None,  # noqa: ARG001 — Preserve signature; edge-tts does not support express-as
) -> str:
    """Synthesize speech and return a base64-encoded MP3.

    Prefer ``Communicate(text, voice, rate=, pitch=)``; on failure, fall back to default prosody;
    raise an error if that also fails. The ``style`` parameter is retained for compatibility and is actually mapped to rate/pitch by the caller.
    """
    del style  # edge-tts cannot be injected into express-as, the sentiment has been reflected in rate/pitch
    plain = plain_text_for_tts(text)
    if not plain:
        return ""
    import edge_tts

    voice_id = voice or DEFAULT_VOICE
    attempts: list[tuple[str, object]] = [
        ("prosody", edge_tts.Communicate(plain, voice_id, rate=rate, pitch=pitch)),
        ("plain", edge_tts.Communicate(plain, voice_id)),
    ]

    last_err: Exception | None = None
    for label, communicate in attempts:
        try:
            audio_bytes = await _stream_communicate(communicate)
            if audio_bytes:
                if label != "prosody":
                    logger.debug(
                        "Edge TTS downgraded to plain text voice=%s rate=%s", voice_id, rate
                    )
                return base64.b64encode(audio_bytes).decode("ascii")
        except Exception as e:
            last_err = e
            logger.info("Edge TTS path failed label=%s: %s", label, e)
            continue

    if last_err:
        raise RuntimeError(f"Edge TTS synthesis failed: {last_err}") from last_err
    raise RuntimeError("Edge TTS returns empty audio")


async def synthesize_to_base64_safe(
    text: str,
    voice: str | None = None,
    *,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    style: str | None = None,
) -> str:
    """Synthesize speech; if failed, log and return an empty string (compatible with old calls)."""
    try:
        return await synthesize_to_base64(
            text, voice, rate=rate, pitch=pitch, style=style
        )
    except Exception as e:
        logger.error("Edge TTS failed: %s", e)
        return ""
