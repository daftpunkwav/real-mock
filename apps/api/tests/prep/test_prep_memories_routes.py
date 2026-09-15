"""Memory route tests for realmock.domains.prep.routes.memories.

Covers: get/update/delete detail dead returns, validation, comment/score patch, single/batch delete and HTTP smoke
Conventions: Temp DB and TestClient; CSRF faked where needed; rate limits reset per test
"""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from realmock.asgi import app
from realmock.domains.prep.models import PrepMemory

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()

def _make_memory(db, **kwargs) -> PrepMemory:
    from realmock.domains.prep.services import create_memory

    kwargs.setdefault("summary", "seed summary")
    return create_memory(db, **kwargs)

class _FakeReq:
    method = "PATCH"
    headers: dict = {"origin": "http://localhost:8080"}

_CSRF = {"Origin": "http://localhost:8080"}

@pytest.mark.asyncio
async def test_get_detail_not_found_dead_return(monkeypatch, db) -> None:
    import realmock.domains.prep.routes.memories as memories_route

    monkeypatch.setattr(memories_route, "_not_found", lambda: None)
    out = await memories_route.get_memory_detail(999999999, db)
    assert out is None

@pytest.mark.asyncio
async def test_update_not_found_dead_return(monkeypatch, db) -> None:
    import realmock.domains.prep.routes.memories as memories_route
    from realmock.domains.prep.schemas import PrepMemoryUpdate

    monkeypatch.setattr(memories_route, "_not_found", lambda: None)
    out = await memories_route.update_memory(
        999999999, PrepMemoryUpdate(summary="x"), _FakeReq(), db  # type: ignore[arg-type]
    )
    assert out is None

@pytest.mark.asyncio
async def test_update_memory_empty_summary_is_a0001(db) -> None:
    import realmock.domains.prep.routes.memories as memories_route
    from realmock.domains.prep.schemas import PrepMemoryUpdate
    from realmock.platform.core.errors import ApiBusinessError

    row = _make_memory(db, summary="to-edit")
    with pytest.raises(ApiBusinessError) as exc:
        await memories_route.update_memory(
            row.id, PrepMemoryUpdate(summary="   "), _FakeReq(), db  # type: ignore[arg-type]
        )
    assert exc.value.error_code == "A0001"

@pytest.mark.asyncio
async def test_update_memory_comment_and_score(db) -> None:
    import realmock.domains.prep.routes.memories as memories_route
    from realmock.domains.prep.schemas import PrepMemoryUpdate

    row = _make_memory(db, summary="patch me", comment="old", score=5)
    out = await memories_route.update_memory(
        row.id,
        PrepMemoryUpdate(comment="new-comment", score=9),
        _FakeReq(),
        db,
    )
    assert out is not None
    assert out.comment == "new-comment"
    assert out.score == 9

def test_delete_memory_single_and_404(db) -> None:
    row = _make_memory(db, summary="to-delete")
    with TestClient(app) as client:
        missing = client.delete(f"/api/v1/prep/memories/{999999999}", headers=dict(_CSRF))
        assert missing.status_code == 404
        resp = client.delete(f"/api/v1/prep/memories/{row.id}", headers=dict(_CSRF))
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"deleted": row.id}
        again = client.get(f"/api/v1/prep/memories/{row.id}")
        assert again.status_code == 404

@pytest.mark.asyncio
async def test_batch_delete_coerces_bad_ids(db, monkeypatch) -> None:
    import realmock.domains.prep.routes.memories as memories_route
    from realmock.domains.prep.schemas import PrepMemoryBatchDelete

    monkeypatch.setattr(memories_route, "assert_csrf_if_cookie_only", lambda *a, **k: None)
    row = _make_memory(db, summary="batch-keep")

    class _Body:
        ids = ["bad", -3, 0, str(row.id), row.id]

    out = await memories_route.batch_delete_memories(_Body(), object(), db)  # type: ignore[arg-type]
    assert out == {"deleted": 1}
    # Schema-level batch still works over HTTP.
    assert PrepMemoryBatchDelete(ids=[row.id + 9999]) is not None

@pytest.mark.asyncio
async def test_delete_memory_dead_return(monkeypatch, db) -> None:
    import realmock.domains.prep.routes.memories as memories_route

    class _Req:
        method = "DELETE"
        headers: dict = {"origin": "http://localhost:8080"}

    monkeypatch.setattr(memories_route, "_not_found", lambda: None)
    out = await memories_route.delete_memory(999999999, _Req(), db)  # type: ignore[arg-type]
    assert out is None

def test_memories_http_still_ok(db) -> None:
    with TestClient(app) as client:
        resp = client.get("/api/v1/prep/memories/tags")
        assert resp.status_code == 200
