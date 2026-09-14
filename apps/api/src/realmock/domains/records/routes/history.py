"""History routes: session list and ledger replay via session catalog."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from realmock.domains.records.schemas.history import SessionHistoryItem
from realmock.platform.contracts.session_catalog import (
    get_session_catalog,
    snapshot_from_catalog_dict,
)
from realmock.platform.core.errors import raise_error
from realmock.platform.core.session_auth import assert_session_token, extract_token
from realmock.platform.database import get_sessions_db

router = APIRouter()


@router.get("/sessions", response_model=list[SessionHistoryItem])
def list_sessions(db: Session = Depends(get_sessions_db)):
    """List interview sessions (metadata only) via the session catalog port."""
    catalog = get_session_catalog()
    items = catalog.list_sessions(db)
    return [SessionHistoryItem.model_validate(item.model_dump()) for item in items]


@router.get("/sessions/{session_id}/ledger")
def get_session_ledger(
    session_id: int,
    db: Session = Depends(get_sessions_db),
    access: str | None = Depends(extract_token),
):
    """Return the frozen (or prefix) ledger for replay UI."""
    catalog = get_session_catalog()
    raw = catalog.get_session_snapshot(db, session_id)
    if raw is None:
        raise_error("A2001")
    snap = snapshot_from_catalog_dict(raw)
    assert_session_token(snap, access)
    ledger = catalog.get_ledger(db, session_id)
    if ledger is None:
        raise_error("A2001")
    return ledger
