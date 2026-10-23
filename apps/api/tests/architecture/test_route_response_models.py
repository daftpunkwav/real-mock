"""Contract guard: every published operation declares the shape it returns.

The OpenAPI document is what clients read, so the guard asserts on the
published contract (``app.openapi()``) instead of on the route objects: an
operation whose 2xx response declares ``application/json`` with an empty
schema publishes an untyped object, the generated frontend types carry
``unknown``, and a backend shape change reaches the browser unchecked.

Responses that are not JSON carry their own media type (server-sent events,
``image/png``, binary downloads) and need no JSON schema. Operations listed
in ``_UNTYPED_ALLOWLIST`` are intentionally untyped and state why.
"""

from __future__ import annotations

from typing import Any

from realmock.asgi import app

# Operations published without a JSON response schema, with the reason each
# exemption exists. Keys are the operation without its mount prefix, so one
# entry covers both the ``/api/v1`` mount and the legacy ``/api`` alias.
_UNTYPED_ALLOWLIST: dict[str, str] = {
    "GET /records/sessions/{session_id}/ledger": (
        "the ledger carries historical rows that may not validate against a "
        "strict model, and the lenient corrupt-row tolerance is deliberate"
    ),
}

_JSON_MEDIA_TYPE = "application/json"
_HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "trace")
_MOUNT_PREFIXES = ("/api/v1", "/api")


def _operation_key(method: str, path: str) -> str:
    """Build the allowlist key of one operation, without the mount prefix."""
    for prefix in _MOUNT_PREFIXES:
        if path.startswith(f"{prefix}/"):
            return f"{method} {path[len(prefix) :]}"
    return f"{method} {path}"


def _success_responses(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Return (method, path, response) for every 2xx response of the document."""
    found: list[tuple[str, str, dict[str, Any]]] = []
    for path, item in (spec.get("paths") or {}).items():
        for method, operation in item.items():
            if method.lower() not in _HTTP_METHODS:
                continue
            for code, response in (operation.get("responses") or {}).items():
                if str(code).startswith("2"):
                    found.append((method.upper(), path, response))
    return found


def _untyped_json_operations(spec: dict[str, Any]) -> list[str]:
    """Return the operations whose JSON success response has no schema."""
    untyped: list[str] = []
    for method, path, response in _success_responses(spec):
        json_content = (response.get("content") or {}).get(_JSON_MEDIA_TYPE)
        if json_content is None:
            continue
        if not json_content.get("schema"):
            untyped.append(_operation_key(method, path))
    return sorted(untyped)


def test_every_json_operation_declares_a_response_shape() -> None:
    untyped = _untyped_json_operations(app.openapi())
    unexempted = [operation for operation in untyped if operation not in _UNTYPED_ALLOWLIST]
    assert not unexempted, (
        "operations published with an untyped application/json response (the "
        f"contract tells clients nothing about them): {unexempted}; declare a "
        "response_model or the real media type, or add a justified entry to "
        "_UNTYPED_ALLOWLIST"
    )


def test_allowlist_entries_are_still_untyped() -> None:
    """Every exemption must still be an untyped operation (no stale entries)."""
    untyped = _untyped_json_operations(app.openapi())
    stale = sorted(operation for operation in _UNTYPED_ALLOWLIST if operation not in untyped)
    assert not stale, (
        f"allowlist entries no longer describe an untyped operation: {stale}; "
        "remove them (and their reason) once the operation declares a shape"
    )


def test_guard_inspects_every_published_path() -> None:
    """The guard must see the published operations, not just a subset."""
    spec = app.openapi()
    paths = set(spec.get("paths") or {})
    inspected = {path for _, path, _ in _success_responses(spec)}
    assert paths, "the OpenAPI document publishes no path"
    assert inspected == paths, (
        f"published paths without an inspected success response: {sorted(paths - inspected)}"
    )
