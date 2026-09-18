"""Interview-session event types.

Note ``SessionEvent.schema_version``: increment it whenever the event protocol changes; the frontend
can use it for compatibility checks. Session snapshots live in
:mod:``realmock.domains.interview.realtime.nudge.snapshot``.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TurnState(str, Enum):
    AI_SPEAKING = "AI_SPEAKING"
    USER_SPEAKING = "USER_SPEAKING"
    PROCESSING = "PROCESSING"
    IDLE = "IDLE"


@dataclass
class SessionEvent:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Event protocol version, +1 when evolving; ws_handler is injected in the first event
    schema_version: int = 1


__all__ = ["TurnState", "SessionEvent"]
