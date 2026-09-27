"""Interview-session event types.

Turn-state machine values for the realtime turn protocol. Session snapshots
live in :mod:``realmock.domains.interview.realtime.nudge.snapshot``; the wire
event shapes are declared in ``protocol/interview_ws.schema.json``.
"""

from enum import Enum


class TurnState(str, Enum):
    AI_SPEAKING = "AI_SPEAKING"
    USER_SPEAKING = "USER_SPEAKING"
    PROCESSING = "PROCESSING"
    IDLE = "IDLE"


__all__ = ["TurnState"]
