"""Contract guard tests for src/realmock/domains/resume/services/contract_guard.py.

Covers: assert_resume_contract_aligned happy path plus drift branches for
response fields, leaked private columns, missing JSON columns, filename/file-type
lengths, allowed extensions, upload bytes, MIME map, dimension keys/hints/weights,
locale literal/locales, and limits payload.
Conventions: no real network/model downloads (all clients mocked); no DB; rate
limits reset per test.
"""
from __future__ import annotations

import pytest

import realmock.domains.resume.services.contract_guard as guard_mod


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()


def test_happy_path_aligned() -> None:
    guard_mod.assert_resume_contract_aligned()


def test_unmapped_response_field(monkeypatch) -> None:
    fields = dict(guard_mod.ResumeResponse.model_fields)
    fields["ghost_field_xyz"] = fields[next(iter(fields))]
    monkeypatch.setattr(guard_mod.ResumeResponse, "model_fields", fields)
    with pytest.raises(RuntimeError, match="no ORM column"):
        guard_mod.assert_resume_contract_aligned()


def test_leaked_private_column(monkeypatch) -> None:
    fields = dict(guard_mod.ResumeResponse.model_fields)
    # Inject a private ORM column object as a field value; only the key matters.
    fields["raw_text"] = fields[next(iter(fields))]
    monkeypatch.setattr(guard_mod.ResumeResponse, "model_fields", fields)
    with pytest.raises(RuntimeError, match="leaked private"):
        guard_mod.assert_resume_contract_aligned()


def test_missing_json_column(monkeypatch) -> None:
    cols = {k: v for k, v in guard_mod.Resume.__table__.columns.items() if k != "parsed_profile"}
    monkeypatch.setattr(guard_mod.Resume.__table__, "columns", cols)
    with pytest.raises(RuntimeError, match="missing JSON"):
        guard_mod.assert_resume_contract_aligned()


def test_length_drift(monkeypatch) -> None:
    monkeypatch.setattr(guard_mod, "FILENAME_MAX_LENGTH", 10**9)
    with pytest.raises(RuntimeError, match="max_length"):
        guard_mod.assert_resume_contract_aligned()


def test_file_type_length_drift(monkeypatch) -> None:
    monkeypatch.setattr(guard_mod, "FILE_TYPE_MAX_LENGTH", 10**9)
    with pytest.raises(RuntimeError, match="max_length"):
        guard_mod.assert_resume_contract_aligned()


def test_allowed_extensions_identity(monkeypatch) -> None:
    copied = frozenset(x for x in guard_mod.ALLOWED_EXTENSIONS)
    assert copied is not guard_mod.ALLOWED_EXTENSIONS
    monkeypatch.setattr(guard_mod, "ALLOWED_EXTENSIONS", copied)
    with pytest.raises(RuntimeError, match="ALLOWED_EXTENSIONS drifted"):
        guard_mod.assert_resume_contract_aligned()


def test_max_upload_drift(monkeypatch) -> None:
    monkeypatch.setattr(guard_mod, "MAX_UPLOAD_BYTES", guard_mod.MAX_UPLOAD_BYTES + 1)
    with pytest.raises(RuntimeError, match="MAX_UPLOAD_BYTES drifted"):
        guard_mod.assert_resume_contract_aligned()


def test_mime_missing_and_extra(monkeypatch) -> None:
    orig = dict(guard_mod.FILE_MIME)
    monkeypatch.setattr(guard_mod, "FILE_MIME", {})
    with pytest.raises(RuntimeError, match="FILE_MIME missing"):
        guard_mod.assert_resume_contract_aligned()
    extra = dict(orig)
    extra["exe"] = "application/x-exe"
    monkeypatch.setattr(guard_mod, "FILE_MIME", extra)
    with pytest.raises(RuntimeError, match="not in ALLOWED_EXTENSIONS"):
        guard_mod.assert_resume_contract_aligned()


def test_dimension_dup_and_hint_drift(monkeypatch) -> None:
    keys = list(guard_mod.DIMENSION_KEYS)
    monkeypatch.setattr(guard_mod, "DIMENSION_KEYS", keys + [keys[0]])
    with pytest.raises(RuntimeError, match="duplicates"):
        guard_mod.assert_resume_contract_aligned()


def test_hint_keys_drift(monkeypatch) -> None:
    hints = dict(guard_mod.DIMENSION_HINTS)
    hints.pop(next(iter(hints)))
    monkeypatch.setattr(guard_mod, "DIMENSION_HINTS", hints)
    with pytest.raises(RuntimeError, match="DIMENSION_HINTS drift"):
        guard_mod.assert_resume_contract_aligned()


def test_weights_keys_drift(monkeypatch) -> None:
    w = dict(guard_mod.DIMENSION_WEIGHTS)
    w.pop(next(iter(w)))
    monkeypatch.setattr(guard_mod, "DIMENSION_WEIGHTS", w)
    with pytest.raises(RuntimeError, match="DIMENSION_WEIGHTS drift"):
        guard_mod.assert_resume_contract_aligned()


def test_weights_non_positive(monkeypatch) -> None:
    w = dict(guard_mod.DIMENSION_WEIGHTS)
    w[next(iter(w))] = 0
    monkeypatch.setattr(guard_mod, "DIMENSION_WEIGHTS", w)
    with pytest.raises(RuntimeError, match="non-positive"):
        guard_mod.assert_resume_contract_aligned()


@pytest.mark.asyncio
async def test_locale_not_literal(monkeypatch) -> None:
    monkeypatch.setattr(guard_mod, "get_args", lambda ann: ())
    with pytest.raises(RuntimeError, match="not a Literal"):
        guard_mod.assert_resume_contract_aligned()


def test_locale_drift(monkeypatch) -> None:
    monkeypatch.setattr(guard_mod, "ANALYSIS_LOCALES", ("zh-CN",))
    with pytest.raises(RuntimeError, match="locale drift"):
        guard_mod.assert_resume_contract_aligned()


def test_limits_payload_drift(monkeypatch) -> None:
    monkeypatch.setattr(guard_mod, "client_limits_payload", lambda: {"only_one": 1})
    with pytest.raises(RuntimeError, match="key drift"):
        guard_mod.assert_resume_contract_aligned()
