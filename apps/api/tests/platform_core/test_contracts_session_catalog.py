"""Catalog contract tests for realmock.platform.contracts.session_catalog.

Covers: empty-catalog defaults and register/get/set round-trip.
Conventions: in-memory fakes only; global catalog restored after test.
"""

from __future__ import annotations

from unittest.mock import MagicMock


class TestSessionCatalogContract:
    def test_catalog_defaults_and_register(self) -> None:
        from realmock.platform.contracts.session_catalog import (
            _EmptySessionCatalog,
            get_session_catalog,
            register_session_catalog,
            set_session_catalog,
            snapshot_from_catalog_dict,
        )

        empty = _EmptySessionCatalog()
        assert empty.list_sessions(MagicMock()) == []
        assert empty.get_session(MagicMock(), 1) is None
        assert empty.get_session_snapshot(MagicMock(), 1) is None
        assert empty.get_ledger(MagicMock(), 1) is None
        assert empty.get_process_context(MagicMock(), 1) == ""

        prev = get_session_catalog()

        class _Cat(_EmptySessionCatalog):
            pass

        cat = _Cat()
        register_session_catalog(cat)
        assert get_session_catalog() is cat
        set_session_catalog(prev)
        snap = snapshot_from_catalog_dict({"id": 1, "role": "r", "level": "l", "company": "c", "status": "done"})
        assert snap.id == 1
