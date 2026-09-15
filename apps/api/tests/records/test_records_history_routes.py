"""History route tests for realmock.domains.records.routes.history.

Covers: session list via catalog and ledger missing/success/forbidden branches
Conventions: get_session_catalog faked; TestClient for HTTP; rate limits reset per test
"""
from __future__ import annotations
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
import realmock.domains.records.routes.history as hist_mod
from realmock.asgi import app
from realmock.platform.contracts.session_catalog import SessionCatalogItem
from realmock.platform.core.ratelimit import reset_rate_limit

@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()

def _item(**over) -> SessionCatalogItem:
    base = {
        "id": 1, "role": "Backend", "level": "Senior", "company": "acme",
        "status": "completed", "current_phase": "summary",
    }
    base.update(over)
    return SessionCatalogItem.model_validate(base)

def test_list_sessions_via_catalog(db) -> None:
    cat = MagicMock()
    cat.list_sessions.return_value = [_item(id=1), _item(id=2, role="Frontend")]
    with patch.object(hist_mod, "get_session_catalog", return_value=cat):
        with TestClient(app) as client:
            resp = client.get("/api/v1/records/sessions")
    assert resp.status_code == 200
    assert [r["id"] for r in resp.json()] == [1, 2]

def test_ledger_missing_snapshot_is_404(db) -> None:
    cat = MagicMock()
    cat.get_session_snapshot.return_value = None
    with patch.object(hist_mod, "get_session_catalog", return_value=cat):
        with TestClient(app) as client:
            resp = client.get("/api/v1/records/sessions/1/ledger")
    assert resp.status_code == 404

def test_ledger_missing_ledger_is_404(db) -> None:
    snap = {"id": 1, "access_token": None, "messages": "[]"}
    cat = MagicMock()
    cat.get_session_snapshot.return_value = snap
    cat.get_ledger.return_value = None
    with patch.object(hist_mod, "get_session_catalog", return_value=cat):
        with patch.object(hist_mod, "assert_session_token", return_value=None):
            with TestClient(app) as client:
                resp = client.get("/api/v1/records/sessions/1/ledger")
    assert resp.status_code == 404

def test_ledger_success_returns_payload(db) -> None:
    snap = {"id": 1, "access_token": None, "messages": "[]"}
    cat = MagicMock()
    cat.get_session_snapshot.return_value = snap
    cat.get_ledger.return_value = {"frozen": True, "turns": []}
    with patch.object(hist_mod, "get_session_catalog", return_value=cat):
        with patch.object(hist_mod, "assert_session_token", return_value=None):
            with TestClient(app) as client:
                resp = client.get("/api/v1/records/sessions/1/ledger")
    assert resp.status_code == 200
    assert resp.json() == {"frozen": True, "turns": []}

def test_ledger_token_mismatch_is_403(db) -> None:
    snap = {"id": 1, "access_token": "secret-token-xyz", "messages": "[]"}
    cat = MagicMock()
    cat.get_session_snapshot.return_value = snap
    cat.get_ledger.return_value = {"frozen": True}
    with patch.object(hist_mod, "get_session_catalog", return_value=cat):
        with TestClient(app) as client:
            resp = client.get("/api/v1/records/sessions/1/ledger")
    assert resp.status_code == 403
