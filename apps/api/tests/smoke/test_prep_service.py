"""Smoke: prep service imports standalone and mounts /prep routes."""

from __future__ import annotations


def test_service_routes_registered() -> None:
    from realmock.domains.prep.main import app

    paths = set(app.openapi()["paths"].keys())
    assert any(p.startswith("/api/v1/prep") for p in paths)


def test_service_title() -> None:
    from realmock.domains.prep.main import app

    assert app.title == "Prep Service"
