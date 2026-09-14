"""Turn coordination (WS mixin): turn lock and candidate turns; streaming/side effects delegated to child mixins.

This module only composes:

- :mod:`turn_lock` — turn lock (reject closing / busy+epoch validation / release only this epoch);
- :mod:`turn_text_entry` — admit candidate text into a turn (``stt_final`` before the main flow);
- :mod:`turn_stt_finish` — finish a voice turn (PCM limit / loopback capture / failure count);
- :mod:`turn_playback` — playback waiting (generation alignment, wait for playback before opening the microphone).

``_AUDIO_BUFFER_MAX_BYTES`` and ``_IMAGE_BASE64_MAX_LEN`` are re-exported by this module
(preserving test patch / import paths).
"""

from __future__ import annotations

from realmock.domains.interview.realtime.turn.control import TurnControlMixin
from realmock.domains.interview.realtime.turn.lock import TurnLockMixin
from realmock.domains.interview.realtime.turn.playback import TurnPlaybackMixin
from realmock.domains.interview.realtime.turn.stt_finish import (
    TurnSttFinishMixin,
    _AUDIO_BUFFER_MAX_BYTES,
)
from realmock.domains.interview.realtime.turn.streaming import TurnStreamingMixin, _IMAGE_BASE64_MAX_LEN
from realmock.domains.interview.realtime.turn.text_entry import TurnTextEntryMixin


class TurnCoordinatorMixin(
    TurnLockMixin,
    TurnTextEntryMixin,
    TurnSttFinishMixin,
    TurnPlaybackMixin,
    TurnStreamingMixin,
    TurnControlMixin,
):
    """Candidate round entry; combines streaming consumption with interruption/ending side effects."""


__all__ = [
    "TurnCoordinatorMixin",
    "TurnLockMixin",
    "TurnTextEntryMixin",
    "TurnSttFinishMixin",
    "TurnPlaybackMixin",
    "_AUDIO_BUFFER_MAX_BYTES",
    "_IMAGE_BASE64_MAX_LEN",
]
