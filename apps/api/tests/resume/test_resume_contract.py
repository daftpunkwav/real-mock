"""Resume contract guard, locale helper, and GET /resume/limits.

Keeps DIMENSION_HINTS / FILE_MIME aligned with the catalog the frontend reads.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.domains.resume.schemas.limits import (
    ALLOWED_EXTENSIONS,
    ANALYSIS_LOCALES,
    DIMENSION_KEYS,
    MAX_PARALLEL_ANALYZE,
    MAX_UPLOAD_BYTES,
    client_limits_payload,
)
from realmock.domains.resume.schemas.locale import (
    infer_resume_text_locale,
    normalize_analysis_locale,
)
from realmock.domains.resume.services.contract_guard import assert_resume_contract_aligned


def test_contract_guard_accepts_current_models() -> None:
    assert_resume_contract_aligned()


def test_contract_guard_rejects_hint_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    from realmock.domains.resume.services import contract_guard

    drifted = dict(contract_guard.DIMENSION_HINTS)
    drifted["not_a_dimension"] = "x"
    monkeypatch.setattr(contract_guard, "DIMENSION_HINTS", drifted)
    with pytest.raises(RuntimeError, match="DIMENSION_HINTS"):
        contract_guard.assert_resume_contract_aligned()


def test_contract_guard_rejects_weight_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    from realmock.domains.resume.services import contract_guard

    drifted = dict(contract_guard.DIMENSION_WEIGHTS)
    drifted["not_a_dimension"] = 2.0
    monkeypatch.setattr(contract_guard, "DIMENSION_WEIGHTS", drifted)
    with pytest.raises(RuntimeError, match="DIMENSION_WEIGHTS"):
        contract_guard.assert_resume_contract_aligned()

    zeroed = {k: 0.0 for k in contract_guard.DIMENSION_KEYS}
    monkeypatch.setattr(contract_guard, "DIMENSION_WEIGHTS", zeroed)
    with pytest.raises(RuntimeError, match="non-positive"):
        contract_guard.assert_resume_contract_aligned()


def test_normalize_analysis_locale() -> None:
    assert normalize_analysis_locale(None) == "zh-CN"
    assert normalize_analysis_locale("  ") == "zh-CN"
    assert normalize_analysis_locale("en") == "en"
    assert normalize_analysis_locale("zh-CN") == "zh-CN"
    assert normalize_analysis_locale("fr") == "zh-CN"


def test_infer_resume_text_locale_from_body() -> None:
    chinese = (
        "熟悉 Python 与 FastAPI，曾负责招聘系统后端，主导性能优化、"
        "接口设计和面试流程改进。"
    )
    english = (
        "Senior software engineer with eight years building distributed "
        "backends in Python and FastAPI."
    )
    assert infer_resume_text_locale(chinese) == "zh-CN"
    assert infer_resume_text_locale(english) == "en"
    assert infer_resume_text_locale("Ada Lee — software engineer resume") == "en"
    assert infer_resume_text_locale(None, "", "  ") == "zh-CN"


def test_contract_guard_rejects_extra_mime(monkeypatch: pytest.MonkeyPatch) -> None:
    from realmock.domains.resume.services import contract_guard

    drifted = dict(contract_guard.FILE_MIME)
    drifted["doc"] = "application/msword"
    monkeypatch.setattr(contract_guard, "FILE_MIME", drifted)
    with pytest.raises(RuntimeError, match="FILE_MIME has extensions"):
        contract_guard.assert_resume_contract_aligned()


def test_analyze_request_empty_locale_defaults() -> None:
    from realmock.domains.resume.schemas.request import ResumeAnalyzeRequest

    assert ResumeAnalyzeRequest.model_validate({}).locale == "zh-CN"
    assert ResumeAnalyzeRequest.model_validate({"locale": ""}).locale == "zh-CN"
    assert ResumeAnalyzeRequest.model_validate({"locale": "  "}).locale == "zh-CN"
    assert ResumeAnalyzeRequest.model_validate({"locale": "en"}).locale == "en"


def test_extract_reexports_file_lookup() -> None:
    from realmock.domains.resume.services import extract, files

    assert extract.find_resume_files is files.find_resume_files
    assert extract.find_resume_file is files.find_resume_file


def test_get_resume_limits_matches_catalog() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/v1/resume/limits")
    assert resp.status_code == 200
    body = resp.json()
    expected = client_limits_payload()
    assert body == expected
    assert body["max_parallel_analyze"] == MAX_PARALLEL_ANALYZE
    assert body["max_upload_bytes"] == MAX_UPLOAD_BYTES
    assert set(body["allowed_extensions"]) == set(ALLOWED_EXTENSIONS)
    assert body["dimension_keys"] == list(DIMENSION_KEYS)
    assert body["analysis_locales"] == list(ANALYSIS_LOCALES)
    assert body["max_resume_versions"] == expected["max_resume_versions"]
