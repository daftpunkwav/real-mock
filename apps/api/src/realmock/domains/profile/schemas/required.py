"""Profile required-field constants and Annotated constraints.

Aligned with frontend ``profileFields.REQUIRED_KEYS`` (string keys only;
``tech_domains`` is a list and is constrained on the Update model, not here).

Lengths come from field_meta — do not duplicate max_length numbers here.
Aliases are hand-written so IDEs and Pydantic see stable names.

Must not import FastAPI, ORM, or the Update/Response models.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, StringConstraints

from realmock.domains.profile.schemas.field_meta import (
    FIELD_MAX_LENGTH,
    REQUIRED_STRING_FIELDS,
)

__all__ = [
    "REQUIRED_STRING_FIELDS",
    "RequiredIdentity",
    "RequiredJobDirection",
    "RequiredName",
    "RequiredSelfIntro",
    "RequiredTargetRole",
    "strip_nonblank",
]


def strip_nonblank(value: object) -> object:
    """Strip required strings; pure whitespace becomes empty so min_length rejects it."""
    if not isinstance(value, str):
        return value
    return value.strip()


RequiredName = Annotated[
    str,
    BeforeValidator(strip_nonblank),
    StringConstraints(min_length=1, max_length=FIELD_MAX_LENGTH["name"]),
]
RequiredIdentity = Annotated[
    str,
    BeforeValidator(strip_nonblank),
    StringConstraints(min_length=1, max_length=FIELD_MAX_LENGTH["identity"]),
]
RequiredJobDirection = Annotated[
    str,
    BeforeValidator(strip_nonblank),
    StringConstraints(min_length=1, max_length=FIELD_MAX_LENGTH["job_direction"]),
]
RequiredTargetRole = Annotated[
    str,
    BeforeValidator(strip_nonblank),
    StringConstraints(min_length=1, max_length=FIELD_MAX_LENGTH["target_role"]),
]
RequiredSelfIntro = Annotated[
    str,
    BeforeValidator(strip_nonblank),
    StringConstraints(min_length=1, max_length=FIELD_MAX_LENGTH["self_intro"]),
]
