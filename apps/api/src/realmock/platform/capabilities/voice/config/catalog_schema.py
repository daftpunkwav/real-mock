"""Voice catalog table structures: type aliases and provider factory ``_p``.

Extracted from :mod:`...config.catalog`; the three provider tables and the main module import ``_p`` from this module.
"""

from __future__ import annotations

from typing import Any, Literal

RecognizeVia = Literal["native_audio", "transcribe_only", "none"]
SpeakVia = Literal["native_audio", "tts_from_text", "none"]
ProviderStatus = Literal["ready", "coming_soon"]


def _p(
    *,
    id: str,
    label: str,
    can_speech_recognize: bool = False,
    can_interview_reason: bool = False,
    can_speech_speak: bool = False,
    recognize_via: RecognizeVia = "none",
    speak_via: SpeakVia = "none",
    status: ProviderStatus = "ready",
    default_model: str = "",
    default_api_base: str = "",
    hint: str = "",
    vendor: str = "",
) -> dict[str, Any]:
    return {
        "id": id,
        "label": label,
        "can_speech_recognize": can_speech_recognize,
        "can_interview_reason": can_interview_reason,
        "can_speech_speak": can_speech_speak,
        "recognize_via": recognize_via,
        "speak_via": speak_via,
        "status": status,
        "default_model": default_model,
        "default_api_base": default_api_base,
        "hint": hint,
        # Vendor group id (see platform.vendors); "" = not a vendor entry (custom/local/none).
        "vendor": vendor,
    }
