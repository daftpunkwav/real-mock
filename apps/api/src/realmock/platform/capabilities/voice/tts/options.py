"""TTS voice static catalogs (owned by the voice capability layer).

Keeps AVATARS / TTS_VOICES here so voice resolution does not depend on the
interview-domain options module.
"""

from __future__ import annotations

AVATARS = [
    {
        "id": "professional_male",
        "name": "Professional Male Interviewer",
        "voice": "zh-CN-YunyangNeural",
    },
    {"id": "senior_male", "name": "Senior Male Interviewer", "voice": "zh-CN-YunjianNeural"},
    {"id": "strict_expert", "name": "Strict Technical Expert", "voice": "zh-CN-YunjianNeural"},
    {"id": "gentle_female", "name": "Gentle Female Interviewer", "voice": "zh-CN-XiaoxiaoNeural"},
    {"id": "hr_female", "name": "HR Female Interviewer", "voice": "zh-CN-XiaoyiNeural"},
    {"id": "young_female", "name": "Young Female Interviewer", "voice": "zh-CN-XiaoxiaoNeural"},
]

_AVATAR_GENDER = {
    "professional_male": "male",
    "senior_male": "male",
    "strict_expert": "male",
    "gentle_female": "female",
    "hr_female": "female",
    "young_female": "female",
}


def avatar_gender(avatar_id: str) -> str:
    """Interviewer gender for an avatar id ("female"/"male"/"" when unknown).

    Single source of truth for prompt-side facts and the voice-gender guard
    test: every female avatar must resolve to a female voice in EVERY vendor
    mapping.
    """
    return _AVATAR_GENDER.get((avatar_id or "").strip(), "")


TTS_VOICES = [
    {"id": "zh-CN-XiaoxiaoNeural", "name": "Xiaoxiao (female)"},
    {"id": "zh-CN-YunxiNeural", "name": "Yunxi (male)"},
    {"id": "zh-CN-YunyangNeural", "name": "Yunyang (professional male)"},
    {"id": "zh-CN-XiaoyiNeural", "name": "Xiaoyi (lively female)"},
    {"id": "zh-CN-YunjianNeural", "name": "Yunjian (steady male)"},
]
