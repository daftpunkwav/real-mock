"""Outbound port: project debrief overall_score onto interview session rows.

Read catalog stays separate (``session_catalog``). Composition root registers
the interview-backed implementation; records calls this after debrief ready.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@runtime_checkable
class SessionScoreProjectionPort(Protocol):
    """Write-only score projection owned by the interview session store."""

    def apply_overall_score(self, db: Session, session_id: int, score: int) -> None:
        """Persist ``overall_score`` for history lists / WS complete events."""
        ...


class _NoopScoreProjection:
    """Default until composition root registers a real adapter."""

    def apply_overall_score(self, db: Session, session_id: int, score: int) -> None:
        logger.debug(
            "score projection noop sid=%s score=%s (adapter not registered)",
            session_id,
            score,
        )


_projection: SessionScoreProjectionPort = _NoopScoreProjection()


def register_session_score_projection(port: SessionScoreProjectionPort) -> None:
    """Register the interview score-projection adapter (composition root)."""
    global _projection
    _projection = port


def get_session_score_projection() -> SessionScoreProjectionPort:
    """Return the registered score projection port (never None)."""
    return _projection


def apply_session_overall_score(db: Session, session_id: int, score: int) -> None:
    """Convenience wrapper used by records after debrief persist."""
    get_session_score_projection().apply_overall_score(db, session_id, int(score))


__all__ = [
    "SessionScoreProjectionPort",
    "apply_session_overall_score",
    "get_session_score_projection",
    "register_session_score_projection",
]
