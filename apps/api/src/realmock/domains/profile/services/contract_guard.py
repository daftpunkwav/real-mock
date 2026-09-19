"""Profile contract ↔ ORM column drift guard (fails at import time).

``assert_profile_contract_aligned`` is called from ``routes.profile`` at import
so a drifted contract cannot reach the store's setattr loop.

Checks (in order):
1. Every ``UserProfileUpdate`` field has an ORM column (no unmapped PUT keys).
2. Each string field's schema ``max_length`` is not larger than the VARCHAR length.
3. ``field_meta.FIELD_MAX_LENGTH`` keys and lengths match Update string fields,
   and ``tech_domains`` max count matches ``TECH_DOMAINS_MAX_COUNT``.
4. ``UserProfileResponse`` fields minus ``id`` / ``updated_at`` equal Update fields.

(1) + (3) together imply FIELD_MAX_LENGTH keys are ORM columns: meta is aligned
with Update, Update is a subset of the table. SQLite does not enforce VARCHAR
length, so check 2 is a contract alarm, not a database constraint.
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import String

from realmock.platform.models import UserProfile
from realmock.domains.profile.schemas import UserProfileResponse, UserProfileUpdate
from realmock.domains.profile.schemas.field_meta import FIELD_MAX_LENGTH, TECH_DOMAINS_MAX_COUNT


def _contract_max_length(field: Any) -> int | None:
    """Read max_length declared on a contract field; None if undeclared."""
    for meta in field.metadata:
        max_length = getattr(meta, "max_length", None)
        if max_length is not None:
            return max_length
    # FieldInfo-level constraints (not Annotated metadata)
    return getattr(field, "max_length", None)


def assert_profile_contract_aligned() -> None:
    """Raise RuntimeError if Update / Response / field_meta / ORM lengths drifted."""
    unmapped = set(UserProfileUpdate.model_fields) - set(UserProfile.__table__.columns.keys())
    if unmapped:
        raise RuntimeError(f"UserProfileUpdate has fields with no ORM column: {sorted(unmapped)}")

    length_drift: list[str] = []
    for name, field in UserProfileUpdate.model_fields.items():
        if name == "tech_domains":
            continue
        schema_max = _contract_max_length(field)
        # All guarded columns are VARCHAR; .length lives on String.
        orm_len = cast("String", UserProfile.__table__.columns[name].type).length
        if schema_max is not None and orm_len is not None and schema_max > orm_len:
            length_drift.append(f"{name}: schema={schema_max} > orm={orm_len}")
    if length_drift:
        raise RuntimeError(f"Contract max_length exceeds ORM column declaration: {length_drift}")

    string_fields = set(UserProfileUpdate.model_fields) - {"tech_domains"}
    meta_keys = set(FIELD_MAX_LENGTH)
    if string_fields != meta_keys:
        raise RuntimeError(
            "field_meta.FIELD_MAX_LENGTH drift vs UserProfileUpdate: "
            f"missing={sorted(string_fields - meta_keys)} extra={sorted(meta_keys - string_fields)}"
        )

    meta_length_drift: list[str] = []
    for name in sorted(string_fields):
        schema_max = _contract_max_length(UserProfileUpdate.model_fields[name])
        meta_max = FIELD_MAX_LENGTH[name]
        if schema_max != meta_max:
            meta_length_drift.append(f"{name}: schema={schema_max} meta={meta_max}")
    tech_max = _contract_max_length(UserProfileUpdate.model_fields["tech_domains"])
    if tech_max != TECH_DOMAINS_MAX_COUNT:
        meta_length_drift.append(
            f"tech_domains: schema={tech_max} meta={TECH_DOMAINS_MAX_COUNT}"
        )
    if meta_length_drift:
        raise RuntimeError(
            f"field_meta max_length drift vs UserProfileUpdate: {meta_length_drift}"
        )

    response_only = {"id", "updated_at"}
    update_keys = set(UserProfileUpdate.model_fields)
    response_keys = set(UserProfileResponse.model_fields)
    if response_keys - response_only != update_keys:
        raise RuntimeError(
            "UserProfileResponse / UserProfileUpdate field-set drift: "
            f"response_extra={sorted(response_keys - response_only - update_keys)} "
            f"update_extra={sorted(update_keys - (response_keys - response_only))}"
        )
