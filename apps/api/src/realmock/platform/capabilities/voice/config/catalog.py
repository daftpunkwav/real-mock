"""Three-stage voice/reasoning provider capability catalogs (shared semantics across backend and frontend).

The table schema and ``_p`` factory live in :mod:`.catalog_schema`; the three tables live in
``reasoning_providers`` / ``recognize_providers`` / ``speak_providers`` respectively.
This module aggregates exports and implements ``catalog_payload`` / ``find_provider``.
"""

from __future__ import annotations

from typing import Any

from .reasoning_providers import REASONING_PROVIDERS
from .recognize_providers import RECOGNIZE_PROVIDERS
from .speak_providers import SPEAK_PROVIDERS

__all__ = [
    "REASONING_PROVIDERS",
    "RECOGNIZE_PROVIDERS",
    "SPEAK_PROVIDERS",
    "catalog_payload",
    "find_provider",
    "non_reasoning_provider_ids",
]


def catalog_payload() -> dict[str, Any]:
    return {
        "reasoning": REASONING_PROVIDERS,
        "recognize": RECOGNIZE_PROVIDERS,
        "speak": SPEAK_PROVIDERS,
    }


def find_provider(stage: str, provider_id: str) -> dict[str, Any] | None:
    mapping = {
        "reasoning": REASONING_PROVIDERS,
        "recognize": RECOGNIZE_PROVIDERS,
        "speak": SPEAK_PROVIDERS,
    }
    for p in mapping.get(stage, []):
        if p["id"] == provider_id:
            return p
    return None


def non_reasoning_provider_ids() -> frozenset[str]:
    """Set of provider ids that cannot perform "interview reasoning" (single source of truth, derived from the catalogs).

    = all ids in the recognize/speak catalogs − ids declared reasoning-capable in the reasoning catalog.
    Used by settings-save validation to reject "assigning an ASR/TTS provider to the reason stage";
    adding a voice provider requires only updating the catalog tables, and this set follows automatically.
    """
    reason_capable = {
        p["id"]
        for p in REASONING_PROVIDERS
        if p.get("can_interview_reason")
    }
    voice_only = {
        p["id"]
        for table in (RECOGNIZE_PROVIDERS, SPEAK_PROVIDERS)
        for p in table
    }
    return frozenset(voice_only - reason_capable)
