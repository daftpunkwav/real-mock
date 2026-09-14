"""Interview turn event type definitions.

Provide a unified streaming contract between runner and ws_handler so the handler does not access the agent's private state directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EventKind(str, Enum):
    """All event types pushed to the upper layer by the runner."""

    TOKEN = "token"               # Streaming token
    TURN_COMPLETE = "turn_done"   # Completed in a single round (with complete text and stage information)
    ERROR = "error"               # abnormal


@dataclass(frozen=True)
class StreamEvent:
    """runner -> event carrier for ws_handler/API."""

    kind: EventKind
    token: str = ""
    content: str = ""             # Full text (populated only for TURN_COMPLETE; plain text under say protocol)
    phase_id: str = ""            # current stage id
    is_complete: bool = False     # Whether the interview is complete (interview_complete)
    phase_changed: bool = False   # Whether the phase has been switched this round
    emotion: str = "neutral"      # Emotion tag (turn protocol emotion field)
    error: str = ""               # error message
    error_code: str = ""          # Business error code; defaults to B0001 on frontend when empty
    error_retryable: bool = False # Is it possible to retry
    wait_seconds: int = 0         # The number of seconds the candidate is expected to answer (0=not provided)
    sources: tuple[str, ...] = () # Basis for answering this round (resume/github/company_kb/none)
    result: str | None = None     # Agent verdict announced on the wrap-up turn (passed/failed)
    phase_title: str = ""         # Display title of the current plan step (agent-authored; empty = static id)

    @classmethod
    def make_token(cls, token: str) -> "StreamEvent":
        return cls(kind=EventKind.TOKEN, token=token)

    @classmethod
    def make_turn_done(
        cls,
        *,
        content: str,
        phase_id: str,
        is_complete: bool,
        phase_changed: bool,
        emotion: str = "neutral",
        wait_seconds: int = 0,
        sources: tuple[str, ...] = (),
        result: str | None = None,
        phase_title: str = "",
    ) -> "StreamEvent":
        return cls(
            kind=EventKind.TURN_COMPLETE,
            content=content,
            phase_id=phase_id,
            is_complete=is_complete,
            phase_changed=phase_changed,
            emotion=emotion,
            wait_seconds=wait_seconds,
            sources=sources,
            result=result,
            phase_title=phase_title,
        )

    @classmethod
    def make_error(
        cls,
        message: str,
        *,
        code: str = "",
        retryable: bool = False,
    ) -> "StreamEvent":
        """Construct error event. code is the business error code; when it is empty, the front end will display it as B0001."""
        return cls(
            kind=EventKind.ERROR,
            error=message,
            error_code=code,
            error_retryable=retryable,
        )


__all__ = ["EventKind", "StreamEvent"]