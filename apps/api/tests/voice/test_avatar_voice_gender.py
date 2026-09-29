"""Voice-gender consistency guard: every avatar's declared gender must match
the voice each vendor mapping resolves to.

This pins the class of bug where a female interviewer persona ended up with a
male voice: round personas now pick avatars (round_chain), and these mapping
tables are what keep the look and the voice aligned. Adding a new avatar
without updating a vendor map fails here instead of shipping a mismatched
voice.
"""

from __future__ import annotations

from realmock.platform.capabilities.voice.tts.options import AVATARS, avatar_gender
from realmock.platform.capabilities.voice.tts.providers.minimax import (
    DEFAULT_VOICE,
    resolve_minimax_voice,
)

EDGE_FEMALE_VOICES = {"zh-CN-XiaoxiaoNeural", "zh-CN-XiaoyiNeural"}
EDGE_MALE_VOICES = {"zh-CN-YunxiNeural", "zh-CN-YunyangNeural", "zh-CN-YunjianNeural"}


def _minimax_voice_matches_gender(voice: str, gender: str) -> bool:
    if gender == "female":
        return voice.startswith("female-") or voice == "presenter_female"
    return voice.startswith("male-") or voice == "presenter_male"


def test_every_avatar_voice_matches_gender_across_vendors() -> None:
    for avatar in AVATARS:
        aid = avatar["id"]
        gender = avatar_gender(aid)
        assert gender in ("male", "female"), f"{aid}: gender must be declared"

        # Edge catalog: the avatar's bound voice must match its gender.
        edge_voice = avatar["voice"]
        expected = EDGE_FEMALE_VOICES if gender == "female" else EDGE_MALE_VOICES
        assert edge_voice in expected, (
            f"{aid}: edge voice {edge_voice} contradicts gender '{gender}'"
        )

        # MiniMax: an explicit per-avatar mapping must exist (falling through
        # to the vendor default would silently hand one gender's voice to the
        # other) and the mapped voice must match the gender.
        mm_voice = resolve_minimax_voice(aid, None)
        assert mm_voice != DEFAULT_VOICE, (
            f"{aid}: no explicit minimax avatar_map entry (fell back to default)"
        )
        assert _minimax_voice_matches_gender(mm_voice, gender), (
            f"{aid}: minimax voice {mm_voice} contradicts gender '{gender}'"
        )


def test_avatar_gender_lookup_is_total_for_catalog() -> None:
    """Every catalog avatar has a gender entry; unknown ids resolve empty."""
    assert {avatar["id"] for avatar in AVATARS} <= {
        aid
        for aid in ("professional_male", "senior_male", "strict_expert",
                    "gentle_female", "hr_female", "young_female")
        if avatar_gender(aid)
    }
    assert avatar_gender("mystery_avatar") == ""
    assert avatar_gender("") == ""
