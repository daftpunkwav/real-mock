"""Voice resolve tests for src/realmock/platform/capabilities/voice/tts/voice_resolve.py.

Covers: _combine_percent/_combine_hz bad-input branches, resolve_session_voice
avatar/settings/default branches, resolve_prosody strictness/emotion/personality
branches, with_emotion/voice_label branches.
Conventions: no real network/model downloads (all clients mocked); pure logic;
rate limits reset per test.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()


def test_combine_percent_bad_input() -> None:
    from realmock.platform.capabilities.voice.tts import voice_resolve as vr

    # Both unparsable -> 0.
    assert vr._combine_percent("bad", "worse") == "+0%"
    assert vr._combine_percent("+10%", "-3%") == "+7%"
    assert vr._combine_percent("-10%", "+3%") == "-7%"


def test_combine_hz_bad_input() -> None:
    from realmock.platform.capabilities.voice.tts import voice_resolve as vr

    assert vr._combine_hz("bad", "worse") == "+0Hz"
    assert vr._combine_hz("+5Hz", "-2Hz") == "+3Hz"
    assert vr._combine_hz(None, None) == "+0Hz"  # type: ignore[arg-type]


def test_resolve_session_voice_branches() -> None:
    from realmock.platform.capabilities.voice.tts import voice_resolve as vr
    from realmock.platform.capabilities.voice.tts.providers.edge import DEFAULT_VOICE

    # Avatar mapped wins.
    first_avatar = next(iter(vr._AVATAR_VOICE))
    assert vr.resolve_session_voice(first_avatar) == vr._AVATAR_VOICE[first_avatar]
    # Settings voice fallback.
    assert vr.resolve_session_voice(None, "custom-voice") == "custom-voice"
    assert vr.resolve_session_voice("  ", "  ") == DEFAULT_VOICE


@pytest.mark.asyncio
async def test_resolve_prosody_strictness_and_emotion() -> None:
    from realmock.platform.capabilities.voice.tts import voice_resolve as vr

    # strictness unparsable -> default 3 (no adjustment).
    p = vr.resolve_prosody(avatar_id=None, personality="professional", strictness="bad", emotion="neutral")  # type: ignore[arg-type]
    assert p.rate == "+0%"
    high = vr.resolve_prosody(avatar_id=None, personality="pressure", strictness=9, emotion="happy")
    assert high.rate != "+0%" or high.pitch != "+0Hz"
    low = vr.resolve_prosody(avatar_id=None, personality="gentle", strictness=1, emotion="sad")
    assert low.rate.startswith("-") or low.pitch.startswith("-")
    # Unknown personality falls back to professional.
    unk = vr.resolve_prosody(avatar_id=None, personality="nope", strictness=3)
    pro = vr.resolve_prosody(avatar_id=None, personality="professional", strictness=3)
    assert unk.rate == pro.rate


def test_with_emotion_and_label() -> None:
    from realmock.platform.capabilities.voice.tts import voice_resolve as vr

    base = vr.resolve_prosody(avatar_id=None, personality="professional", strictness=3)
    assert vr.with_emotion(base, "neutral") is base
    assert vr.with_emotion(base, "unknown-emo") is base
    happy = vr.with_emotion(base, "happy")
    assert happy.rate != base.rate or happy.pitch != base.pitch
    assert vr.voice_label("no-such-voice") == "no-such-voice"
