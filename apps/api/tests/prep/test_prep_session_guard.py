"""Session-guard tests for realmock.domains.prep.services.session_guard.

Covers: the shared prep session admission rules (missing session A3001,
wrong capability token A0401, completed session A3002) and the order in
which they are applied.
Conventions: real sessions DB; rate limits reset per test
"""

from __future__ import annotations

import json

import pytest

from realmock.domains.prep.models import PrepSession
from realmock.domains.prep.services.session_guard import (
    load_prep_session,
    require_open_prep_session,
    require_owned_prep_session,
    require_writable_prep_session,
)
from realmock.platform.core.errors import ApiBusinessError
from realmock.platform.core.session_auth import new_access_token


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()


def _session(db, **kwargs) -> PrepSession:
    kwargs.setdefault("status", "active")
    kwargs.setdefault("messages", json.dumps([], ensure_ascii=False))
    kwargs.setdefault("access_token", new_access_token())
    row = PrepSession(**kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_load_prep_session_missing(db) -> None:
    """An unknown session is A3001."""
    with pytest.raises(ApiBusinessError) as exc:
        load_prep_session(db, 999)
    assert exc.value.error_code == "A3001"


def test_require_writable_prep_session_missing_and_completed(db) -> None:
    """The owner-level guard: unknown session A3001, completed session A3002."""
    with pytest.raises(ApiBusinessError) as exc:
        require_writable_prep_session(db, 999999999)
    assert exc.value.error_code == "A3001"

    row = _session(db)
    row.status = "completed"
    db.commit()
    with pytest.raises(ApiBusinessError) as exc2:
        require_writable_prep_session(db, row.id)
    assert exc2.value.error_code == "A3002"


def test_require_owned_prep_session_checks_the_capability_token(db) -> None:
    """A wrong capability token is refused with A0401."""
    row = _session(db)
    with pytest.raises(ApiBusinessError) as exc:
        require_owned_prep_session(db, row.id, "not-the-token")
    assert exc.value.error_code == "A0401"


def test_require_open_prep_session_allows_an_open_session(db) -> None:
    """An open session with the right token is admitted."""
    row = _session(db)
    assert require_open_prep_session(db, row.id, row.access_token).id == row.id


def test_require_open_prep_session_refuses_a_completed_session(db) -> None:
    """A completed session refuses a new turn with A3002."""
    row = _session(db)
    row.status = "completed"
    db.commit()
    with pytest.raises(ApiBusinessError) as exc:
        require_open_prep_session(db, row.id, row.access_token)
    assert exc.value.error_code == "A3002"


def test_require_open_prep_session_checks_the_token_before_the_status(db) -> None:
    """Ownership is proven before the session status is judged.

    A caller without the token must not learn whether the session exists
    beyond A3001, so a wrong token on a completed session is A0401.
    """
    row = _session(db)
    row.status = "completed"
    db.commit()
    with pytest.raises(ApiBusinessError) as exc:
        require_open_prep_session(db, row.id, "not-the-token")
    assert exc.value.error_code == "A0401"


def test_linking_an_unknown_target_uses_the_shared_session_rule(db) -> None:
    """The linked target is loaded through the guard, not a second copy of it.

    The unknown-session answer belongs to the guard; a second implementation
    in the linking service would let the two drift apart.
    """
    from realmock.domains.prep.services.linking import apply_session_link

    row = _session(db)
    with pytest.raises(ApiBusinessError) as exc:
        apply_session_link(row, db, 999999999)
    assert exc.value.error_code == "A3001"
