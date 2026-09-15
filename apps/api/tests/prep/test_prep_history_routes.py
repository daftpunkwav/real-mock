"""History route tests for realmock.domains.prep.routes.history.

Covers: writable-session guards, message loading/pruning helpers, summary helpers, compact backup and reason branches, HTTP status mismatches
Conventions: No real LLM; LLM and context faked; temp DB and TestClient where needed; rate limits reset per test
"""
from __future__ import annotations
import json
import pytest
from fastapi.testclient import TestClient
from realmock.asgi import app
from realmock.domains.prep.models import PrepSession
from realmock.platform.core.session_auth import new_access_token

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()

def _session(db, messages: list[dict] | str = "[]", **kwargs) -> PrepSession:
    kwargs.setdefault("status", "active")
    if isinstance(messages, str):
        kwargs["messages"] = messages
    else:
        kwargs["messages"] = json.dumps(messages, ensure_ascii=False)
    kwargs.setdefault("access_token", new_access_token())
    row = PrepSession(**kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

def test_require_writable_missing_and_completed(db) -> None:
    import realmock.domains.prep.routes.history as history_mod
    from realmock.platform.core.errors import ApiBusinessError

    with pytest.raises(ApiBusinessError) as exc:
        history_mod._require_existing_writable_session(999999999, db)
    assert exc.value.error_code == "A3001"

    row = _session(db)
    row.status = "completed"
    db.commit()
    with pytest.raises(ApiBusinessError) as exc2:
        history_mod._require_existing_writable_session(row.id, db)
    assert exc2.value.error_code == "A3002"

def test_load_session_messages_corrupt_and_non_list(db) -> None:
    import realmock.domains.prep.routes.history as history_mod

    row = _session(db, messages="not-json{{{")
    assert history_mod._load_session_messages(row) == []
    row2 = _session(db, messages='{"a": 1}')
    assert history_mod._load_session_messages(row2) == []
    row3 = _session(db, messages=[{"role": "user", "content": "hi"}])
    assert len(history_mod._load_session_messages(row3)) == 1

def test_call_ids_and_prune_helpers() -> None:
    import realmock.domains.prep.routes.history as history_mod

    assert history_mod._call_ids({"tool_calls": "bad"}) == []
    assert history_mod._call_ids({"tool_calls": [{"id": "c1"}, "bad"]}) == ["c1"]
    # Trailing assistant with tool_calls is pruned.
    pruned = history_mod._prune_dangling_tool_tail([
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
    ])
    assert pruned == [{"role": "user", "content": "q"}]
    # Orphan tool result without owner is pruned.
    pruned2 = history_mod._prune_dangling_tool_tail([
        {"role": "user", "content": "q"},
        {"role": "tool", "tool_call_id": "missing", "content": "obs"},
    ])
    assert pruned2 == [{"role": "user", "content": "q"}]
    # Complete pair at tail is kept.
    kept = history_mod._prune_dangling_tool_tail([
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "obs"},
    ])
    assert len(kept) == 3

def test_current_summary_empty() -> None:
    import realmock.domains.prep.routes.history as history_mod

    assert history_mod._current_summary([]) == ("", 0)
    assert history_mod._current_summary_text([]) == ""

@pytest.mark.asyncio
async def test_compact_backup_cleanup_on_failure(db, monkeypatch) -> None:
    import realmock.domains.prep.routes.history as history_mod
    from realmock.platform.capabilities.ai.llm.client import LLMClient

    class _LLM:
        context_window = 8000

    monkeypatch.setattr(LLMClient, "from_db", classmethod(lambda cls, *a, **k: _LLM()))
    monkeypatch.setattr(history_mod, "assert_csrf_if_cookie_only", lambda *a, **k: None)

    async def _boom(*args, **kwargs):
        raise RuntimeError("summarizer-down")

    monkeypatch.setattr(history_mod.PrepAgent, "_build_context", _boom)
    row = _session(db, messages=[
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ])

    class _Req:
        method = "POST"
        headers: dict = {}

    before_ids = {r.id for r in db.query(PrepSession).all()}
    with pytest.raises(RuntimeError, match="summarizer-down"):
        await history_mod.compact_prep_session(
            row.id, _Req(), db, db,  # type: ignore[arg-type]
            history_mod.PrepCompactRequest(backup=True),
        )
    after_ids = {r.id for r in db.query(PrepSession).all()}
    assert before_ids == after_ids

@pytest.mark.asyncio
async def test_compact_reason_tool_pairs_only_and_nothing(db, monkeypatch) -> None:
    import realmock.domains.prep.routes.history as history_mod
    from realmock.platform.capabilities.ai.llm.client import LLMClient

    class _LLM:
        context_window = 8000

    monkeypatch.setattr(LLMClient, "from_db", classmethod(lambda cls, *a, **k: _LLM()))
    monkeypatch.setattr(history_mod, "assert_csrf_if_cookie_only", lambda *a, **k: None)
    row = _session(db, messages=[
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
    ])

    async def _smaller(self, **kwargs):
        # Drop one message without writing a summary block.
        return list(self.messages[1:])

    monkeypatch.setattr(history_mod.PrepAgent, "_build_context", _smaller)

    class _Req:
        method = "POST"
        headers: dict = {}

    out = await history_mod.compact_prep_session(
        row.id, _Req(), db, db,  # type: ignore[arg-type]
        history_mod.PrepCompactRequest(backup=False),
    )
    assert out.reason == "tool_pairs_only"

    async def _same(self, **kwargs):
        return list(self.messages)

    monkeypatch.setattr(history_mod.PrepAgent, "_build_context", _same)
    out2 = await history_mod.compact_prep_session(
        row.id, _Req(), db, db,  # type: ignore[arg-type]
        history_mod.PrepCompactRequest(backup=False),
    )
    assert out2.reason == "nothing_to_fold"

def test_update_summary_expected_count_mismatch(db) -> None:
    row = _session(db, messages=[{"role": "user", "content": "hi"}])
    with TestClient(app) as client:
        resp = client.patch(
            f"/api/v1/prep/sessions/{row.id}/summary",
            headers={"Origin": "http://localhost:8080"},
            json={"text": "edited", "expected_message_count": 999},
        )
    assert resp.status_code == 409

def test_update_summary_no_block_is_a3004(db) -> None:
    row = _session(db, messages=[{"role": "user", "content": "hi"}])
    with TestClient(app) as client:
        resp = client.patch(
            f"/api/v1/prep/sessions/{row.id}/summary",
            headers={"Origin": "http://localhost:8080"},
            json={"text": "edited notes"},
        )
    assert resp.status_code == 404

def test_fork_missing_is_404(db) -> None:
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/prep/sessions/999999999/fork",
            json={"up_to": -1},
            headers={"X-Interview-Token": "bad"},
        )
    assert resp.status_code == 404

def test_truncate_expected_count_mismatch(db) -> None:
    row = _session(db, messages=[
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ])
    with TestClient(app) as client:
        resp = client.post(
            f"/api/v1/prep/sessions/{row.id}/messages/truncate",
            headers={"Origin": "http://localhost:8080"},
            json={"from_index": 1, "expected_message_count": 999},
        )
    assert resp.status_code == 409

def test_compact_expected_count_mismatch(db, monkeypatch) -> None:
    from realmock.platform.capabilities.ai.llm.client import LLMClient

    class _LLM:
        context_window = 8000

    monkeypatch.setattr(LLMClient, "from_db", classmethod(lambda cls, *a, **k: _LLM()))
    row = _session(db, messages=[{"role": "user", "content": "hi"}])
    with TestClient(app) as client:
        resp = client.post(
            f"/api/v1/prep/sessions/{row.id}/compact",
            headers={"Origin": "http://localhost:8080"},
            json={"expected_message_count": 999},
        )
    assert resp.status_code == 409
