"""Session-level TTS voice and prosody resolution.

Priority: avatar-mapped voice > voice from credentials (stage_configs extras.tts_voice) > default Xiaoxiao.
personality / strictness affect speaking rate and pitch to reduce flat, mechanical delivery.
"""

from __future__ import annotations

from dataclasses import dataclass

from realmock.platform.capabilities.voice.tts.edge import DEFAULT_VOICE
from realmock.platform.capabilities.voice.tts.options import AVATARS

# avatar_id → Neural voice (kept in sync with options.AVATARS.voice)
_AVATAR_VOICE: dict[str, str] = {
    str(a["id"]): str(a["voice"]) for a in AVATARS if a.get("id") and a.get("voice")
}

# personality → (rate, pitch); edge-tts accepts values such as "+10%" / "-5Hz"
_PERSONALITY_PROSODY: dict[str, tuple[str, str]] = {
    "gentle": ("-6%", "+0Hz"),
    "professional": ("+0%", "+0Hz"),
    "pressure": ("+12%", "+2Hz"),
    "hr": ("-3%", "+1Hz"),
    "expert": ("-4%", "-2Hz"),
}

# emotion tag → additional pitch/rate adjustment (edge-tts does not support express-as)
_EMOTION_PROSODY: dict[str, tuple[str, str]] = {
    "neutral": ("+0%", "+0Hz"),
    "smile": ("+3%", "+3Hz"),
    "happy": ("+5%", "+4Hz"),
    "serious": ("-3%", "-2Hz"),
    "curious": ("+2%", "+2Hz"),
    "encouraging": ("+2%", "+3Hz"),
    "skeptical": ("-2%", "-1Hz"),
    "concerned": ("-4%", "-2Hz"),
    "angry": ("+8%", "+4Hz"),
    "sad": ("-6%", "-3Hz"),
}


@dataclass(frozen=True)
class VoiceProsody:
    """Synthesize the desired timbre and rhythm in a single pass."""

    voice: str
    rate: str = "+0%"
    pitch: str = "+0Hz"
    style: str | None = None  # Reserved field; ignored on the composition side


def resolve_session_voice(
    avatar_id: str | None,
    llm_settings_voice: str | None = None,
) -> str:
    """Parse the Neural patch ID that should be used in this interview."""
    aid = (avatar_id or "").strip()
    if aid and aid in _AVATAR_VOICE:
        return _AVATAR_VOICE[aid]
    settings_voice = (llm_settings_voice or "").strip()
    if settings_voice:
        return settings_voice
    return DEFAULT_VOICE


def _combine_percent(base: str, delta: str) -> str:
    """Add two relative values ​​of the form ``+10%`` / ``-5%``."""
    def _parse(s: str) -> int:
        s = (s or "+0%").strip().replace("%", "")
        try:
            return int(s)
        except ValueError:
            return 0

    total = _parse(base) + _parse(delta)
    sign = "+" if total >= 0 else ""
    return f"{sign}{total}%"


def _combine_hz(base: str, delta: str) -> str:
    def _parse(s: str) -> int:
        s = (s or "+0Hz").strip().replace("Hz", "").replace("hz", "")
        try:
            return int(s)
        except ValueError:
            return 0

    total = _parse(base) + _parse(delta)
    sign = "+" if total >= 0 else ""
    return f"{sign}{total}Hz"


def resolve_prosody(
    *,
    avatar_id: str | None,
    personality: str | None,
    strictness: int | None = None,
    emotion: str | None = None,
    llm_settings_voice: str | None = None,
) -> VoiceProsody:
    """Derive synthesis parameters from avatar / personality / strictness / emotion."""
    voice = resolve_session_voice(avatar_id, llm_settings_voice)
    pers = (personality or "professional").strip().lower()
    rate, pitch = _PERSONALITY_PROSODY.get(pers, _PERSONALITY_PROSODY["professional"])

    # Severity additionally fine-tunes speaking speed (1–10)
    try:
        st = int(strictness) if strictness is not None else 3
    except (TypeError, ValueError):
        st = 3
    if st >= 7:
        rate = _combine_percent(rate, "+5%")
    elif st <= 2:
        rate = _combine_percent(rate, "-3%")

    emo = (emotion or "neutral").strip().lower()
    if emo in _EMOTION_PROSODY:
        er, ep = _EMOTION_PROSODY[emo]
        rate = _combine_percent(rate, er)
        pitch = _combine_hz(pitch, ep)

    return VoiceProsody(voice=voice, rate=rate, pitch=pitch, style=None)


def with_emotion(base: VoiceProsody, emotion: str | None) -> VoiceProsody:
    """Overlaying sentence-level emotional fine-tuning on conversational baseline prosody."""
    emo = (emotion or "neutral").strip().lower()
    if emo not in _EMOTION_PROSODY or emo == "neutral":
        return base
    er, ep = _EMOTION_PROSODY[emo]
    return VoiceProsody(
        voice=base.voice,
        rate=_combine_percent(base.rate, er),
        pitch=_combine_hz(base.pitch, ep),
        style=base.style,
    )


def voice_label(voice_id: str) -> str:
    """Gives a human-readable short name for the sound (for display on the configuration page)."""
    from realmock.platform.capabilities.voice.tts.options import TTS_VOICES

    for v in TTS_VOICES:
        if v.get("id") == voice_id:
            return str(v.get("name") or voice_id)
    return voice_id
