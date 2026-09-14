"""Interview-session event types and snapshots.

Note ``SessionEvent.schema_version``: increment it whenever the event protocol changes; the frontend
can use it for compatibility checks. ``SessionSnapshot`` now belongs to
:mod:``realmock.domains.interview.agents.snapshot`` and is only re-exported here for backward compatibility.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from realmock.domains.interview.agents.snapshot import SessionSnapshot


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


__all__ = ["TurnState", "SessionEvent", "SessionSnapshot"]

# SessionSnapshot has moved to realmock.domains.interview.agents.snapshot; it is re-exported here only for backward compatibility.
# The legacy import from realmock.domains.interview.realtime.core.events import SessionSnapshot still works; new code should directly
# Reference it from realmock.domains.interview.agents.snapshot (dependency direction: realtime → agents only).
