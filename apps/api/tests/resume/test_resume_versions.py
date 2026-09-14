"""HTTP contract for resume family versions."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.domains.resume.schemas.limits import MAX_RESUME_VERSIONS
from realmock.platform.config import get_settings
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _fresh_upload_settings():
    get_settings.cache_clear()
    reset_rate_limit()
    yield
    get_settings.cache_clear()
    reset_rate_limit()


def test_upload_version_shares_family_and_stays_inactive(api_db) -> None:
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/resume/upload",
            files={"file": ("cv.txt", b"version-one", "text/plain")},
        )
        assert first.status_code == 200
        body = first.json()
        assert body["version_n"] == 1
        assert body["family_id"] == body["id"]
        assert body["is_active"] is False

        second = client.post(
            f"/api/v1/resume/{body['id']}/versions",
            files={"file": ("cv-v2.txt", b"version-two", "text/plain")},
        )
        assert second.status_code == 200
        v2 = second.json()
        assert v2["family_id"] == body["family_id"]
        assert v2["version_n"] == 2
        assert v2["is_active"] is False
        assert v2["id"] != body["id"]


def test_upload_version_missing_row_is_a1005(api_db) -> None:
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/resume/999001/versions",
            files={"file": ("cv.txt", b"x", "text/plain")},
        )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "A1005"


def test_upload_version_cap_is_a1008(api_db) -> None:
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/resume/upload",
            files={"file": ("cv.txt", b"v1", "text/plain")},
        )
        assert first.status_code == 200
        anchor_id = first.json()["id"]
        for i in range(2, MAX_RESUME_VERSIONS + 1):
            resp = client.post(
                f"/api/v1/resume/{anchor_id}/versions",
                files={"file": (f"cv-v{i}.txt", f"v{i}".encode(), "text/plain")},
            )
            assert resp.status_code == 200, resp.text
        capped = client.post(
            f"/api/v1/resume/{anchor_id}/versions",
            files={"file": ("cv-overflow.txt", b"too-many", "text/plain")},
        )
    assert capped.status_code == 409
    assert capped.json()["error"]["code"] == "A1008"
