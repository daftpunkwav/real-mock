"""Regression: the resume / prep / report operations publish their real shape.

These operations used to be published as untyped objects, or as JSON while
answering with another media type, so the generated frontend types carried
``unknown``. The assertions below pin the published contract: the component
each JSON operation names and the fields that component carries, plus the
media type of every non-JSON response.
"""

from __future__ import annotations

from typing import Any

import pytest

from realmock.asgi import app

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _spec() -> dict[str, Any]:
    return app.openapi()


def _response(method: str, path: str, code: str = "200") -> dict[str, Any]:
    return _spec()["paths"][path][method]["responses"][code]


def _json_schema(method: str, path: str) -> dict[str, Any]:
    """Return the resolved schema of a JSON success response."""
    schema = _response(method, path)["content"]["application/json"]["schema"]
    if "$ref" not in schema:
        return schema
    ref = schema["$ref"]
    prefix = "#/components/schemas/"
    assert ref.startswith(prefix), ref
    return _spec()["components"]["schemas"][ref[len(prefix) :]]


@pytest.mark.parametrize(
    ("method", "path", "component", "fields"),
    [
        ("delete", "/api/v1/resume/{resume_id}", "ResumeDeleteResponse", {"ok", "id"}),
        (
            "delete",
            "/api/v1/resume/analyses",
            "ResumeAnalysesClearResponse",
            {"ok", "cleared"},
        ),
        (
            "delete",
            "/api/v1/resume/collection",
            "ResumeCollectionDeleteResponse",
            {"ok", "deleted"},
        ),
        (
            "get",
            "/api/v1/resume/{resume_id}/pages",
            "ResumePagesMetaResponse",
            {"pages"},
        ),
        ("delete", "/api/v1/prep/memories/{memory_id}", "PrepDeletedResponse", {"deleted"}),
    ],
)
def test_json_operations_name_a_model_with_their_fields(
    method: str, path: str, component: str, fields: set[str]
) -> None:
    schema = _response(method, path)["content"]["application/json"]["schema"]
    assert schema == {"$ref": f"#/components/schemas/{component}"}
    properties = _json_schema(method, path).get("properties", {})
    assert fields <= set(properties), (
        f"{method.upper()} {path} declares {sorted(properties)}, missing {sorted(fields)}"
    )


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v1/resume/{resume_id}/analyze/stream"),
        ("post", "/api/v1/prep/sessions/{session_id}/message/stream"),
        ("get", "/api/v1/reports/{session_id}/stream"),
    ],
)
def test_sse_operations_declare_the_event_stream(method: str, path: str) -> None:
    content = _response(method, path).get("content") or {}
    assert "text/event-stream" in content, (
        f"{method.upper()} {path} must declare the event-stream media type"
    )
    assert "application/json" not in content, (
        f"{method.upper()} {path} answers with an event stream, not JSON"
    )


def test_resume_file_download_declares_every_served_media_type() -> None:
    content = _response("get", "/api/v1/resume/{resume_id}/file").get("content") or {}
    assert "application/json" not in content
    assert set(content) == {
        "application/pdf",
        _DOCX_MIME,
        "text/markdown",
        "text/plain",
        "application/octet-stream",
    }


def test_resume_page_image_declares_png() -> None:
    content = _response("get", "/api/v1/resume/{resume_id}/pages/{page_no}").get("content") or {}
    assert set(content) == {"image/png"}
    assert content["image/png"]["schema"] == {"type": "string", "format": "binary"}


def test_records_ledger_stays_untyped() -> None:
    """The ledger keeps its deliberate lenient contract (see the guard allowlist)."""
    content = _response("get", "/api/v1/records/sessions/{session_id}/ledger").get("content") or {}
    assert content["application/json"]["schema"] == {}
