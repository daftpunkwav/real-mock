"""Voice-channel prompt directive + vendor-aware voice resolution tests.

The directive tells the thinking model what its TTS channel can render: MiniMax
speech-2.8 models vocalize interjection tags like ``(laughs)``; unsupported models
must stay plain text; non-MiniMax handlers get no directive at all.
"""

from __future__ import annotations

from realmock.domains.interview.agents import voice_prompt_directive
from realmock.platform.capabilities.voice.tts import TtsCredentials
from realmock.platform.capabilities.voice.tts.voice_resolve import (
    resolve_prosody,
    resolve_session_voice,
)


def test_minimax_28_directive_lists_interjection_tags():
    creds = TtsCredentials(handler="minimax_speech", model="speech-2.8-hd")
    directive = voice_prompt_directive(creds)
    assert "## Voice channel" in directive
    assert "(laughs)" in directive
    assert "(emm)" in directive
    # Restraint rules are part of the contract.
    assert "1-2" in directive


def test_minimax_26_directive_forbids_tags():
    creds = TtsCredentials(handler="minimax_speech", model="speech-2.6-hd")
    directive = voice_prompt_directive(creds)
    assert "does NOT support" in directive
    assert "never emit" in directive


def test_non_minimax_handler_gets_no_directive():
    assert voice_prompt_directive(TtsCredentials(handler="edge")) == ""


def test_minimax_unknown_model_gets_forbid_directive():
    for model in ("", "speech-unknown", "speech-2.6-hd"):
        directive = voice_prompt_directive(TtsCredentials(handler="minimax_speech", model=model))
        assert "does NOT support" in directive
        assert "never emit" in directive


def test_minimax_voice_resolves_via_avatar_map():
    prosody = resolve_prosody(
        avatar_id="hr_female", personality="hr", handler="minimax_speech"
    )
    assert prosody.voice == "female-chengshu"


def test_minimax_voice_passthrough_only_for_vendor_voice_ids():
    # A vendor-native settings voice is kept as-is.
    assert (
        resolve_session_voice(None, "female-yujie", handler="minimax_speech")
        == "female-yujie"
    )
    # An Edge neural id is ignored so the avatar/default mapping stays in charge.
    assert (
        resolve_session_voice(None, "zh-CN-XiaoxiaoNeural", handler="minimax_speech")
        == "male-qn-qingse"
    )


def test_edge_handler_keeps_neural_voice_resolution():
    assert resolve_session_voice("hr_female", None) == "zh-CN-XiaoyiNeural"
