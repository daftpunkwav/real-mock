"""Resume contract ↔ ORM / catalog drift guard (fails at import time).

``assert_resume_contract_aligned`` is called from ``routes.router`` at import
so a drifted catalog cannot reach upload, CRUD, or analysis.

Checks (in order):
1. ``ResumeResponse`` fields are a subset of ORM columns plus JSON-mapped names
   (``parsed_profile`` / ``analysis`` are JSON text columns, not extra tables).
2. Filename / file_type catalog max lengths do not exceed ORM VARCHAR lengths.
3. Domain upload aliases match platform protocol constants.
4. FILE_MIME keys equal ALLOWED_EXTENSIONS (no missing, no extras).
5. DIMENSION_KEYS are unique; DIMENSION_HINTS and DIMENSION_WEIGHTS keys match exactly.
6. DIMENSION_WEIGHTS values are all positive.
7. ANALYSIS_LOCALES match ``ResumeAnalyzeRequest.locale`` Literal values.
8. ``ResumeDomainLimits`` fields equal ``client_limits_payload()`` keys.

Must not run business logic or touch the database.
"""

from __future__ import annotations

from typing import cast, get_args

from sqlalchemy import String

from realmock.platform.core.constants import (
    RESUME_ALLOWED_EXTENSIONS,
    RESUME_MAX_UPLOAD_BYTES,
)
from realmock.platform.models import Resume
from realmock.domains.resume.schemas.limits import (
    ALLOWED_EXTENSIONS,
    ANALYSIS_LOCALES,
    DIMENSION_HINTS,
    DIMENSION_KEYS,
    DIMENSION_WEIGHTS,
    FILE_MIME,
    FILE_TYPE_MAX_LENGTH,
    FILENAME_MAX_LENGTH,
    MAX_UPLOAD_BYTES,
    client_limits_payload,
)
from realmock.domains.resume.schemas.request import ResumeAnalyzeRequest
from realmock.domains.resume.schemas.response import ResumeDomainLimits, ResumeResponse

# JSON-encoded ORM text columns that the HTTP response exposes as structured fields.
_JSON_RESPONSE_FIELDS = frozenset({"parsed_profile", "analysis"})
# ORM-only columns that must never appear on ResumeResponse.
_ORM_PRIVATE = frozenset({"profile_id", "raw_text"})


def assert_resume_contract_aligned() -> None:
    """Raise RuntimeError if response / catalog / ORM lengths drifted."""
    orm_cols = set(Resume.__table__.columns.keys())
    response_keys = set(ResumeResponse.model_fields)
    unmapped = (response_keys - _JSON_RESPONSE_FIELDS) - orm_cols
    if unmapped:
        raise RuntimeError(f"ResumeResponse has fields with no ORM column: {sorted(unmapped)}")

    leaked = response_keys & _ORM_PRIVATE
    if leaked:
        raise RuntimeError(f"ResumeResponse leaked private ORM columns: {sorted(leaked)}")

    missing_json = _JSON_RESPONSE_FIELDS - orm_cols
    if missing_json:
        raise RuntimeError(f"Resume ORM missing JSON text columns: {sorted(missing_json)}")

    length_drift: list[str] = []
    # Both columns are VARCHAR (declared on the ORM model); .length lives on String.
    filename_orm = cast("String", Resume.__table__.columns["filename"].type).length
    file_type_orm = cast("String", Resume.__table__.columns["file_type"].type).length
    if filename_orm is not None and FILENAME_MAX_LENGTH > filename_orm:
        length_drift.append(f"filename: catalog={FILENAME_MAX_LENGTH} > orm={filename_orm}")
    if file_type_orm is not None and FILE_TYPE_MAX_LENGTH > file_type_orm:
        length_drift.append(f"file_type: catalog={FILE_TYPE_MAX_LENGTH} > orm={file_type_orm}")
    if length_drift:
        raise RuntimeError(f"Contract max_length exceeds ORM column declaration: {length_drift}")

    # Identity (not equality) is intentional: the domain catalog must alias the
    # platform object, so any copy-paste refactor fails fast here at startup.
    if ALLOWED_EXTENSIONS is not RESUME_ALLOWED_EXTENSIONS:
        raise RuntimeError("limits.ALLOWED_EXTENSIONS drifted from platform RESUME_ALLOWED_EXTENSIONS")
    if MAX_UPLOAD_BYTES != RESUME_MAX_UPLOAD_BYTES:
        raise RuntimeError("limits.MAX_UPLOAD_BYTES drifted from platform RESUME_MAX_UPLOAD_BYTES")

    missing_mime = sorted(ALLOWED_EXTENSIONS - set(FILE_MIME))
    if missing_mime:
        raise RuntimeError(f"FILE_MIME missing allowed extensions: {missing_mime}")
    extra_mime = sorted(set(FILE_MIME) - ALLOWED_EXTENSIONS)
    if extra_mime:
        raise RuntimeError(f"FILE_MIME has extensions not in ALLOWED_EXTENSIONS: {extra_mime}")

    if len(DIMENSION_KEYS) != len(set(DIMENSION_KEYS)):
        raise RuntimeError("DIMENSION_KEYS contains duplicates")
    if set(DIMENSION_HINTS) != set(DIMENSION_KEYS):
        raise RuntimeError(
            "DIMENSION_HINTS drift vs DIMENSION_KEYS: "
            f"missing={sorted(set(DIMENSION_KEYS) - set(DIMENSION_HINTS))} "
            f"extra={sorted(set(DIMENSION_HINTS) - set(DIMENSION_KEYS))}"
        )
    if set(DIMENSION_WEIGHTS) != set(DIMENSION_KEYS):
        raise RuntimeError(
            "DIMENSION_WEIGHTS drift vs DIMENSION_KEYS: "
            f"missing={sorted(set(DIMENSION_KEYS) - set(DIMENSION_WEIGHTS))} "
            f"extra={sorted(set(DIMENSION_WEIGHTS) - set(DIMENSION_KEYS))}"
        )
    non_positive = sorted(k for k, w in DIMENSION_WEIGHTS.items() if not w > 0)
    if non_positive:
        raise RuntimeError(f"DIMENSION_WEIGHTS has non-positive weights: {non_positive}")

    locale_ann = ResumeAnalyzeRequest.model_fields["locale"].annotation
    locale_args = get_args(locale_ann)
    if not locale_args:
        raise RuntimeError(
            f"ResumeAnalyzeRequest.locale is not a Literal (got {locale_ann!r})"
        )
    if set(locale_args) != set(ANALYSIS_LOCALES):
        raise RuntimeError(
            "ResumeAnalyzeRequest.locale drift vs ANALYSIS_LOCALES: "
            f"schema={sorted(locale_args)} catalog={sorted(ANALYSIS_LOCALES)}"
        )

    payload_keys = set(client_limits_payload())
    limits_keys = set(ResumeDomainLimits.model_fields)
    if payload_keys != limits_keys:
        raise RuntimeError(
            "ResumeDomainLimits / client_limits_payload key drift: "
            f"missing={sorted(limits_keys - payload_keys)} extra={sorted(payload_keys - limits_keys)}"
        )
