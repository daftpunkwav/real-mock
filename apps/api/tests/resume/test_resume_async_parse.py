"""Async resume parse lifecycle: background task, retry endpoint, startup sweep.

Contract (since parsing moved out of the upload request):
- Upload returns ``parse_status="pending"`` and the background task fills the row;
- ``POST /resume/{id}/parse`` re-runs a failed row and returns 409 (A1009) while pending;
- Rows stuck ``pending`` after a restart are swept to ``failed`` (B1002) at startup;
- A row deleted before its parse runs is a no-op, never an error.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.domains.resume.services import ingest as ingest_module
from realmock.domains.resume.services.ingest import (
    schedule_resume_parse,
    sweep_stale_pending_parses,
)
from realmock.platform.core.ratelimit import reset_rate_limit
from realmock.platform.models import Resume
from realmock.platform.schemas import CandidateProfile


@pytest.fixture(autouse=True)
def _fresh_upload_settings():
    from realmock.platform.config import get_settings

    get_settings.cache_clear()
    reset_rate_limit()
    yield
    get_settings.cache_clear()
    reset_rate_limit()


def _stub_llm_client(api_key: str) -> type:
    class _StubClient:
        def __init__(self) -> None:
            self.api_key = api_key

    class _StubLLMClient:
        @classmethod
        def from_db(cls, db, **kw):
            return _StubClient()

    return _StubLLMClient


def _poll_parse_status(client: TestClient, resume_id: int) -> tuple[str, str]:
    """Poll ``/list`` until the row's background parse settles; pumps the loop."""
    import time

    status, error = "pending", ""
    for _ in range(300):
        rows = client.get("/api/v1/resume/list").json()
        row = next((r for r in rows if r["id"] == resume_id), None)
        assert row is not None, "uploaded row missing from list"
        status, error = row["parse_status"], row["parse_error"]
        if status != "pending":
            return status, error
        time.sleep(0.02)
    return status, error


def _upload_txt(client: TestClient, name: str = "r.txt", body: bytes = b"Name: A") -> dict:
    resp = client.post(
        "/api/v1/resume/upload",
        files={"file": (name, body, "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_upload_returns_pending_then_done(
    tmp_path, api_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Upload returns pending immediately; the background task lands the parsed row."""
    monkeypatch.setattr(ingest_module, "LLMClient", _stub_llm_client(api_key="k"))

    async def fake_parse(raw_text, llm):
        return CandidateProfile(name="Zhang San")

    monkeypatch.setattr(ingest_module, "parse_resume_with_llm", fake_parse)

    with TestClient(app) as client:
        body = _upload_txt(client)
        assert body["parse_status"] == "pending"
        assert body["parse_error"] == ""

        status, error = _poll_parse_status(client, body["id"])

    assert status == "done"
    assert error == ""
    row = api_db.query(Resume).filter(Resume.id == body["id"]).one()
    assert row.raw_text == "Name: A"
    assert row.parse_status == "done"
    assert row.parse_error == ""


def test_parse_failure_lands_in_row(
    tmp_path, api_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An LLM parse failure marks the row failed instead of surfacing as HTTP 500."""
    monkeypatch.setattr(ingest_module, "LLMClient", _stub_llm_client(api_key="k"))

    async def boom(raw_text, llm):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(ingest_module, "parse_resume_with_llm", boom)

    with TestClient(app) as client:
        body = _upload_txt(client)
        status, error = _poll_parse_status(client, body["id"])

    assert status == "failed"
    assert error == "A1004"
    row = api_db.query(Resume).filter(Resume.id == body["id"]).one()
    assert row.parse_status == "failed"


def test_retry_endpoint_reruns_failed_row(
    tmp_path, api_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /parse on a failed row resets it and reruns the parse to done."""
    monkeypatch.setattr(ingest_module, "LLMClient", _stub_llm_client(api_key="k"))

    calls: list[str] = []

    async def failing(raw_text, llm):
        calls.append(raw_text)
        raise RuntimeError("first attempt dies")

    async def ok(raw_text, llm):
        calls.append(raw_text)
        return CandidateProfile(name="Retried")

    monkeypatch.setattr(ingest_module, "parse_resume_with_llm", failing)

    with TestClient(app) as client:
        body = _upload_txt(client)
        status, _ = _poll_parse_status(client, body["id"])
        assert status == "failed"

        monkeypatch.setattr(ingest_module, "parse_resume_with_llm", ok)
        resp = client.post(f"/api/v1/resume/{body['id']}/parse")
        assert resp.status_code == 200, resp.text
        assert resp.json()["parse_status"] == "pending"

        status, error = _poll_parse_status(client, body["id"])

    assert status == "done"
    assert error == ""
    assert calls == ["Name: A", "Name: A"]


def test_retry_endpoint_409_while_pending(
    tmp_path, api_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /parse while the background task is still running → 409 A1009."""
    monkeypatch.setattr(ingest_module, "LLMClient", _stub_llm_client(api_key="k"))

    import asyncio

    release = asyncio.Event()

    async def slow(raw_text, llm):
        await release.wait()
        return CandidateProfile()

    monkeypatch.setattr(ingest_module, "parse_resume_with_llm", slow)

    with TestClient(app) as client:
        body = _upload_txt(client)

        # The parse task is blocked on the event; while the client portal is
        # alive the task is still pending, so the retry must be rejected.
        resp = client.post(f"/api/v1/resume/{body['id']}/parse")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "A1009"

        release.set()
        status, _ = _poll_parse_status(client, body["id"])

    assert status == "done"


def test_retry_missing_resume_404(api_db) -> None:
    """POST /parse for a nonexistent row → 404 A1005."""
    with TestClient(app) as client:
        resp = client.post("/api/v1/resume/999999/parse")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "A1005"


def test_sweep_marks_stale_pending_failed(api_db) -> None:
    """Startup sweep: pending rows become failed/B1002; done rows untouched."""
    api_db.add(Resume(filename="stuck.txt", file_type="txt", parse_status="pending"))
    api_db.add(Resume(filename="done.txt", file_type="txt", parse_status="done"))
    api_db.commit()

    swept = sweep_stale_pending_parses()

    assert swept == 1
    rows = {r.filename: r for r in api_db.query(Resume).all()}
    assert rows["stuck.txt"].parse_status == "failed"
    assert rows["stuck.txt"].parse_error == "B1002"
    assert rows["done.txt"].parse_status == "done"
    assert rows["done.txt"].parse_error == ""


def test_parse_task_ignores_deleted_row(api_db, monkeypatch: pytest.MonkeyPatch) -> None:
    """A row deleted between scheduling and running is skipped without errors."""
    import asyncio

    monkeypatch.setattr(ingest_module, "LLMClient", _stub_llm_client(api_key="k"))
    row = Resume(filename="gone.txt", file_type="txt", parse_status="pending")
    api_db.add(row)
    api_db.commit()
    row_id = int(row.id)
    api_db.delete(row)
    api_db.commit()

    async def boom(raw_text, llm):
        raise AssertionError("parse must not run for a deleted row")

    monkeypatch.setattr(ingest_module, "parse_resume_with_llm", boom)

    # schedule_resume_parse spawns a task on the running loop; run it to completion.
    async def _drive():
        schedule_resume_parse(row_id)
        from realmock.platform.core import background as _bg
        await asyncio.gather(*_bg._tasks)

    asyncio.run(_drive())

    assert api_db.query(Resume).filter(Resume.id == row_id).count() == 0
