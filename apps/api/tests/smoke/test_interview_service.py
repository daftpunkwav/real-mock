"""Interview domain standalone smoke: importable service and mounted routes.

Reports and growth live in separate domains; interview main only mounts
interview / options / realtime paths.
"""

from __future__ import annotations


def test_service_routes_registered() -> None:
    from realmock.domains.interview.main import app

    paths = set(app.openapi()["paths"].keys())
    assert any(p.startswith("/api/v1/interview") for p in paths)
    assert "/api/v1/options" in paths
    # reports / growth moved out of interview package
    assert not any(p.startswith("/api/v1/reports") for p in paths)
    assert not any(p.startswith("/api/v1/growth") for p in paths)


def test_service_title() -> None:
    from realmock.domains.interview.main import app

    assert app.title == "Interview Service"
