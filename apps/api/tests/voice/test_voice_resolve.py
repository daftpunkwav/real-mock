"""TTS voice resolution and prosody unit tests.

NOTE: manual verification checklist only (not asserted in CI); check during integration testing:
1. Start one session each for Professional Male / Strict Expert / Gentle Female: voices should resemble Yunyang / Yunjian / Xiaoxiao respectively
2. Gentle vs intimidating persona: a perceptible speech-rate difference
3. With markers such as [emotion:smile]: synthesized rate/pitch changes and the Avatar expression stays synchronized
4. When WebGL fails, the CSS portrait mouth follows the audio level without random jitter
5. Text remains available if TTS fails; the tts_playback_done handshake opens the microphone normally
"""

from __future__ import annotations

from realmock.platform.capabilities.voice.tts.voice_resolve import (
    resolve_prosody,
    resolve_session_voice,
    with_emotion,
)


def test_avatar_voice_priority_over_settings():
    assert (
        resolve_session_voice("professional_male", "zh-CN-XiaoxiaoNeural")
        == "zh-CN-YunyangNeural"
    )
    assert (
        resolve_session_voice("gentle_female", "zh-CN-YunyangNeural")
        == "zh-CN-XiaoxiaoNeural"
    )
    assert (
        resolve_session_voice("strict_expert", None) == "zh-CN-YunjianNeural"
    )


def test_fallback_to_settings_then_default():
    assert (
        resolve_session_voice("unknown_avatar", "zh-CN-YunxiNeural")
        == "zh-CN-YunxiNeural"
    )
    assert resolve_session_voice(None, None) == "zh-CN-XiaoxiaoNeural"


def test_personality_prosody_differs():
    gentle = resolve_prosody(
        avatar_id="gentle_female",
        personality="gentle",
        strictness=2,
    )
    pressure = resolve_prosody(
        avatar_id="professional_male",
        personality="pressure",
        strictness=8,
    )
    assert gentle.voice == "zh-CN-XiaoxiaoNeural"
    assert pressure.voice == "zh-CN-YunyangNeural"
    # The gentle persona should be slower (negative %), while the high-pressure persona should be faster
    assert int(gentle.rate.replace("%", "")) < 0
    assert int(pressure.rate.replace("%", "")) > 0


def test_emotion_overlay():
    base = resolve_prosody(
        avatar_id="professional_male",
        personality="professional",
        emotion=None,
    )
    smile = with_emotion(base, "smile")
    serious = with_emotion(base, "serious")
    assert int(smile.pitch.replace("Hz", "")) > int(base.pitch.replace("Hz", "") or "0")
    assert int(serious.rate.replace("%", "")) < int(base.rate.replace("%", "") or "0")
