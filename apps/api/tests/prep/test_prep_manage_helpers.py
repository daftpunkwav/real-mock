"""Manage-helper tests for realmock.domains.prep.routes.manage.

Covers: _require_existing_session missing and _refresh_linked_block bad-JSON, non-list and exception branches
Conventions: DB faked with MagicMock; never raises on corrupt data; rate limits reset per test
"""
from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from realmock.platform.core.ratelimit import reset_rate_limit

@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()

def test_require_existing_missing() -> None:
    import importlib

    mod = importlib.import_module("realmock.domains.prep.routes.manage")

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch.object(mod, "raise_error", side_effect=RuntimeError("A3001")):
        try:
            mod._require_existing_session(999, db)
            assert False
        except RuntimeError:
            pass

def test_refresh_linked_block_bad_json_and_non_list() -> None:
    import importlib

    mod = importlib.import_module("realmock.domains.prep.routes.manage")

    db = MagicMock()
    s1 = SimpleNamespace(id=1, messages="not-json{", linked_session_id=None)
    mod._refresh_linked_block(s1, db)  # type: ignore[arg-type]
    s2 = SimpleNamespace(id=2, messages='{"a": 1}', linked_session_id=None)
    mod._refresh_linked_block(s2, db)  # type: ignore[arg-type]

def test_refresh_linked_block_outer_exception() -> None:
    import importlib

    mod = importlib.import_module("realmock.domains.prep.routes.manage")

    db = MagicMock()
    db.rollback = MagicMock()
    sess = SimpleNamespace(id=3, messages="[]", linked_session_id=2)
    with patch.object(
        mod, "format_linked_session", side_effect=RuntimeError("link down")
    ):
        mod._refresh_linked_block(sess, db)  # type: ignore[arg-type]
    db.rollback.assert_called()
