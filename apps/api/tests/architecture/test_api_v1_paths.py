"""Verify that the ``/api/v1`` and ``/api`` compatibility aliases both exist.

Specifically check that both ``/api/v1/options`` and ``/api/options`` resolve successfully.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client(monkeypatch):
    from realmock.asgi import app
    monkeypatch.setenv("TEST_MODE", "1")
    return TestClient(app)


def test_v1_path_present(monkeypatch) -> None:
    with _client(monkeypatch) as c:
        r = c.get("/api/v1/options")
        assert r.status_code == 200


def test_legacy_alias_present(monkeypatch) -> None:
    """The /api/<sub> compatibility alias remains available; legacy /api alias kept (no expiry in code)."""
    with _client(monkeypatch) as c:
        r = c.get("/api/options")
        assert r.status_code == 200


def test_both_paths_cover_same_endpoint(monkeypatch) -> None:
    """Expose /options on both paths (spot-check, not full set)."""
    with _client(monkeypatch) as c:
        r1 = c.get("/api/v1/options")
        r2 = c.get("/api/options")
        assert r1.status_code == r2.status_code
        # Simple JSON comparison: both endpoints should return the same data
        assert r1.json() == r2.json()


def test_health_unchanged(monkeypatch) -> None:
    """``/health`` is not under the ``/api`` prefix and should remain unchanged."""
    with _client(monkeypatch) as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_interview_style_options_match_schema(monkeypatch) -> None:
    """The interview_style IDs exposed by the options API must match the InterviewConfig schema.

    Regression S-05: options once exposed four choices while the schema allowed only two, causing a 422 submission after the frontend
    selected guided/continuous/challenging.
    """
    from realmock.domains.interview.routes.options_data import INTERVIEW_STYLES
    from realmock.domains.interview.schemas import InterviewConfig

    option_ids = {s["id"] for s in INTERVIEW_STYLES}
    # Extract the allowed literal set from schema field type annotations
    style_field = InterviewConfig.model_fields["interview_style"]
    # The __args__ of the Literal annotation are the allowed values
    allowed = set(style_field.annotation.__args__)
    assert option_ids == allowed, (
        f"options({option_ids}) and schema({allowed}) has an inconsistent interview_style"
    )
    # Every option ID should successfully construct InterviewConfig (without raising ValidationError).
    for style_id in option_ids:
        InterviewConfig(
            role="Backend engineer", level="intermediate", company="bytedance",
            interview_style=style_id,
        )
