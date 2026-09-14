"""Profile contract guard drift-alarm tests.

Each RuntimeError branch of ``assert_profile_contract_aligned`` is triggered via
namespace stubs / monkeypatched metadata so a drifted contract cannot ship
silently. The happy-path alignment check and the HTTP contract live in
test_profile_api.py; pure schema units live in test_profile_schemas.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from realmock.domains.profile.schemas import UserProfileResponse, UserProfileUpdate
from realmock.domains.profile.schemas.field_meta import FIELD_MAX_LENGTH
from realmock.domains.profile.services.contract_guard import (
    _contract_max_length,
    assert_profile_contract_aligned,
)


def test_contract_guard_accepts_current_models() -> None:
    """field_meta, Update, Response, and ORM column lengths stay aligned."""
    assert_profile_contract_aligned()


def test_contract_guard_rejects_unmapped_update_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """An Update field without an ORM column is a PUT setattr loop waiting to crash."""
    from realmock.domains.profile.services import contract_guard

    drifted = dict(UserProfileUpdate.model_fields)
    drifted["ghost_field"] = drifted["city"]
    stub = SimpleNamespace(model_fields=drifted)
    monkeypatch.setattr(contract_guard, "UserProfileUpdate", stub)
    with pytest.raises(RuntimeError, match="ghost_field"):
        contract_guard.assert_profile_contract_aligned()


def test_contract_guard_rejects_schema_max_length_over_orm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A schema max_length above the VARCHAR declaration trips the drift alarm."""
    from realmock.platform.models import UserProfile

    column = UserProfile.__table__.columns["name"]
    monkeypatch.setattr(column.type, "length", 1)
    with pytest.raises(RuntimeError, match="exceeds ORM column declaration"):
        assert_profile_contract_aligned()


def test_contract_guard_rejects_field_meta_key_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    from realmock.domains.profile.services import contract_guard

    drifted = dict(contract_guard.FIELD_MAX_LENGTH)
    del drifted["name"]
    monkeypatch.setattr(contract_guard, "FIELD_MAX_LENGTH", drifted)
    with pytest.raises(RuntimeError, match=r"missing=\['name'\]"):
        contract_guard.assert_profile_contract_aligned()


def test_contract_guard_rejects_field_meta_extra_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from realmock.domains.profile.services import contract_guard

    drifted = dict(contract_guard.FIELD_MAX_LENGTH)
    drifted["ghost_field"] = 10
    monkeypatch.setattr(contract_guard, "FIELD_MAX_LENGTH", drifted)
    with pytest.raises(RuntimeError, match=r"extra=\['ghost_field'\]"):
        contract_guard.assert_profile_contract_aligned()


def test_contract_guard_rejects_field_meta_length_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from realmock.domains.profile.services import contract_guard

    drifted = dict(contract_guard.FIELD_MAX_LENGTH)
    drifted["name"] = 1
    monkeypatch.setattr(contract_guard, "FIELD_MAX_LENGTH", drifted)
    with pytest.raises(RuntimeError, match="name: schema=\\d+ meta=1"):
        contract_guard.assert_profile_contract_aligned()


def test_contract_guard_rejects_tech_domains_count_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from realmock.domains.profile.services import contract_guard

    monkeypatch.setattr(contract_guard, "TECH_DOMAINS_MAX_COUNT", 99)
    with pytest.raises(RuntimeError, match="tech_domains: schema=\\d+ meta=99"):
        contract_guard.assert_profile_contract_aligned()


def test_contract_guard_rejects_response_field_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    """Response keys beyond id/updated_at must mirror Update exactly."""
    from realmock.domains.profile.services import contract_guard

    drifted = dict(UserProfileResponse.model_fields)
    drifted["legacy_field"] = drifted["city"]
    stub = SimpleNamespace(model_fields=drifted)
    monkeypatch.setattr(contract_guard, "UserProfileResponse", stub)
    with pytest.raises(RuntimeError, match="legacy_field"):
        contract_guard.assert_profile_contract_aligned()


def test_contract_max_length_reads_metadata_then_fieldinfo() -> None:
    """Annotated metadata wins; a bare FieldInfo-level constraint is the fallback."""
    assert (
        _contract_max_length(UserProfileUpdate.model_fields["name"])
        == FIELD_MAX_LENGTH["name"]
    )
    # Metadata without max_length, and no FieldInfo-level constraint either.
    assert _contract_max_length(SimpleNamespace(metadata=[object()], max_length=None)) is None
    # Constraint declared on the FieldInfo itself, not in Annotated metadata.
    assert _contract_max_length(SimpleNamespace(metadata=[], max_length=9)) == 9
