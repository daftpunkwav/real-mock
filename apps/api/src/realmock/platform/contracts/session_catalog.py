"""Session catalog port: read-only session / ledger access across domains.

Interview owns ``interview_sessions`` writes and registers the adapter via
:func:`register_session_catalog`. Records (and others) read through
:func:`get_session_catalog` and must not import interview ORM.

Score writes use :mod:`realmock.platform.contracts.session_score` separately.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel
from sqlalchemy.orm import Session


class SessionCatalogItem(BaseModel):
    """History-list row (metadata only; no capability token)."""

    id: int
    role: str
    level: str
    company: str
    workflow_type: str = "technical"
    personality: str = "professional"
    strictness: int = 3
    interview_style: str = "deep_dive"
    avatar_id: str = "professional_male"
    scene_id: str = "meeting_room"
    status: str
    current_phase: str = ""
    overall_score: int | None = None
    process_id: int | None = None
    round_no: int | None = None
    result: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime | None = None
    ledger_frozen: bool = False


# Backward-compatible alias used by records schemas mapping
SessionListItem = SessionCatalogItem


class SessionSnapshot(BaseModel):
    """Normalized session view for auth, report meta, and legacy fallback."""

    id: int
    profile_id: int = 1
    resume_id: int | None = None
    role: str = ""
    level: str = ""
    company: str = ""
    workflow_type: str = "technical"
    personality: str = "professional"
    strictness: int = 3
    interview_style: str = "deep_dive"
    avatar_id: str = "professional_male"
    scene_id: str = "meeting_room"
    status: str = ""
    current_phase: str = ""
    overall_score: int | None = None
    access_token: str | None = None
    process_id: int | None = None
    round_no: int | None = None
    result: str | None = None
    messages: str = "[]"
    report: str = "{}"
    ledger: dict[str, Any] | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime | None = None
    messages_count: int = 0
    duration_seconds: float | None = None
    ledger_frozen: bool = False


@runtime_checkable
class SessionCatalogPort(Protocol):
    """Read-only port implemented by the interview-backed catalog adapter."""

    def list_sessions(self, db: Session) -> list[SessionCatalogItem]:
        """Return session history metadata newest-first."""
        ...

    def get_session(self, db: Session, session_id: int) -> SessionSnapshot | None:
        """Return one typed session snapshot, or None when missing."""
        ...

    def get_session_snapshot(self, db: Session, session_id: int) -> dict[str, Any] | None:
        """Return a JSON-friendly snapshot dict, or None when missing."""
        ...

    def get_ledger(self, db: Session, session_id: int) -> dict[str, Any] | None:
        """Return frozen (or in-progress prefix) ledger, or None."""
        ...

    def get_process_context(self, db: Session, process_id: int) -> str:
        """Render prior-round memory of a multi-round process (empty if unknown)."""
        ...


class _EmptySessionCatalog:
    """Default stub until composition root registers a real adapter."""

    def list_sessions(self, db: Session) -> list[SessionCatalogItem]:
        return []

    def get_session(self, db: Session, session_id: int) -> SessionSnapshot | None:
        return None

    def get_session_snapshot(self, db: Session, session_id: int) -> dict[str, Any] | None:
        return None

    def get_ledger(self, db: Session, session_id: int) -> dict[str, Any] | None:
        return None

    def get_process_context(self, db: Session, process_id: int) -> str:
        return ""


_catalog: SessionCatalogPort = _EmptySessionCatalog()


def register_session_catalog(catalog: SessionCatalogPort) -> None:
    """Register the session catalog implementation (composition root / interview)."""
    global _catalog
    _catalog = catalog


set_session_catalog = register_session_catalog


def get_session_catalog() -> SessionCatalogPort:
    """Return the registered session catalog (never None)."""
    return _catalog


def snapshot_from_catalog_dict(data: dict[str, Any]) -> SessionSnapshot:
    """Best-effort map of ``get_session_snapshot`` dict -> SessionSnapshot."""
    return SessionSnapshot.model_validate(data)


__all__ = [
    "SessionCatalogItem",
    "SessionListItem",
    "SessionSnapshot",
    "SessionCatalogPort",
    "get_session_catalog",
    "register_session_catalog",
    "set_session_catalog",
    "snapshot_from_catalog_dict",
]
