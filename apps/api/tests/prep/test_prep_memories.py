"""Prep memory HTTP routes + session fork/truncate (no network, no LLM)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.domains.prep.models import PrepSession
from realmock.platform.core.session_auth import new_access_token


def _session_with_messages(db, messages: list[dict]) -> PrepSession:
    token = new_access_token()
    session = PrepSession(
        access_token=token,
        status="active",
        messages=json.dumps(messages, ensure_ascii=False),
        target_role="Backend",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _headers(session: PrepSession) -> dict[str, str]:
    return {"X-Interview-Token": session.access_token}


def test_history_coerces_null_content_rows(db) -> None:
    """Loop-internal rows (assistant tool_calls with null content) must not 500 history."""
    session = _session_with_messages(db, [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
        {"role": "assistant", "content": "a1"},
    ])
    with TestClient(app) as client:
        resp = client.get(
            f"/api/v1/prep/sessions/{session.id}/messages",
            headers=_headers(session),
        )
    assert resp.status_code == 200, resp.text
    assert all(isinstance(m["content"], str) for m in resp.json())


# --- memories ---


def test_memory_rating_create_requires_score() -> None:
    with TestClient(app) as client:
        resp = client.post("/api/v1/prep/memories", json={"user_input": "q"})
    assert resp.status_code == 422


def test_memory_crud_and_batch_delete() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/prep/memories",
            json={
                "user_input": "Explain Raft?",
                "agent_output": "Raft is ...",
                "score": 9,
                "reasons": ["无帮助"],
                "comment": "太简略",
                "tags": ["共识", "后端"],
                "origin": "user_rating",
            },
        )
        assert created.status_code == 200, created.text
        mid = created.json()["id"]
        assert created.json()["score"] == 9
        assert created.json()["origin"] == "user_rating"

        listed = client.get("/api/v1/prep/memories")
        assert listed.status_code == 200
        assert any(m["id"] == mid for m in listed.json())

        tags = client.get("/api/v1/prep/memories/tags")
        assert "后端" in tags.json()["tags"]

        detail = client.get(f"/api/v1/prep/memories/{mid}")
        assert detail.json()["comment"] == "太简略"
        assert detail.json()["reasons"] == ["无帮助"]

        patched = client.patch(
            f"/api/v1/prep/memories/{mid}",
            json={"summary": "Edited summary", "tags": ["后端"]},
        )
        assert patched.status_code == 200
        assert patched.json()["summary"] == "Edited summary"
        assert patched.json()["tags"] == ["后端"]

        second = client.post(
            "/api/v1/prep/memories",
            json={"user_input": "q2", "agent_output": "a2", "score": 5},
        )
        second_id = second.json()["id"]

        batch = client.post(
            "/api/v1/prep/memories/batch-delete", json={"ids": [mid, second_id]}
        )
        assert batch.json() == {"deleted": 2}
        assert client.get(f"/api/v1/prep/memories/{mid}").status_code == 404


def test_memory_detail_404() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/prep/memories/999999999").status_code == 404


def test_rating_mirrors_note_into_session_working_memory(db) -> None:
    session = _session_with_messages(db, [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ])
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/prep/memories",
            json={
                "session_id": session.id,
                "user_input": "q1",
                "agent_output": "a1",
                "score": 4,
                "tags": ["后端"],
            },
        )
    assert resp.status_code == 200, resp.text
    db.expire_all()
    messages = json.loads(db.get(PrepSession, session.id).messages)
    assert any(
        m.get("role") == "system" and "User rated a reply 4/10" in str(m.get("content") or "")
        for m in messages
    )


# --- fork / truncate ---


def test_fork_copies_history_through_index(db) -> None:
    session = _session_with_messages(db, [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
    ])
    with TestClient(app) as client:
        resp = client.post(
            f"/api/v1/prep/sessions/{session.id}/fork",
            json={"up_to": 1},
            headers=_headers(session),
        )
    assert resp.status_code == 200, resp.text
    new_id = resp.json()["id"]
    assert new_id != session.id
    db.expire_all()
    forked = db.get(PrepSession, new_id)
    assert forked is not None and forked.status == "active"
    assert json.loads(forked.messages) == [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]


def test_truncate_retracts_user_message_and_replies(db) -> None:
    session = _session_with_messages(db, [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
    ])
    with TestClient(app) as client:
        resp = client.post(
            f"/api/v1/prep/sessions/{session.id}/messages/truncate",
            json={"from_index": 2},
            headers={"Origin": "http://localhost:8080"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"message_count": 2}
    db.expire_all()
    kept = json.loads(db.get(PrepSession, session.id).messages)
    assert [m["content"] for m in kept] == ["q1", "a1"]


def test_truncate_orphan_without_token_succeeds(db) -> None:
    """Regression: clear-messages must not 403 on lost-cookie sessions."""
    session = _session_with_messages(db, [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ])
    session.access_token = ""
    db.commit()
    with TestClient(app) as client:
        resp = client.post(
            f"/api/v1/prep/sessions/{session.id}/messages/truncate",
            json={"from_index": 0},
            headers={"Origin": "http://localhost:8080"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"message_count": 0}


def test_reissue_recovers_cookie_less_session(db) -> None:
    """A listed session with a lost capability token becomes readable again."""
    session = _session_with_messages(db, [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ])
    with TestClient(app) as client:
        # No token anywhere: content read fails with A0401.
        denied = client.get(f"/api/v1/prep/sessions/{session.id}/messages")
        assert denied.status_code == 403, denied.text
        # Owner-level recovery mints a fresh token and seeds the cookie.
        reissued = client.post(
            f"/api/v1/prep/sessions/{session.id}/reissue",
            headers={"Origin": "http://localhost:8080"},
        )
        assert reissued.status_code == 200, reissued.text
        assert reissued.json()["id"] == session.id
        assert f"prep_{session.id}=" in (reissued.headers.get("set-cookie") or "")
        # The same client (cookie jar) can now read history.
        reread = client.get(f"/api/v1/prep/sessions/{session.id}/messages")
        assert reread.status_code == 200, reread.text
        assert [m["content"] for m in reread.json()] == ["q1", "a1"]
    db.expire_all()
    assert db.get(PrepSession, session.id).access_token != ""


def test_truncate_requires_csrf(db) -> None:
    session = _session_with_messages(db, [
        {"role": "user", "content": "q1"},
    ])
    with TestClient(app) as client:
        denied = client.post(
            f"/api/v1/prep/sessions/{session.id}/messages/truncate",
            json={"from_index": 0},
        )
    assert denied.status_code == 403


def test_get_messages_still_requires_token(db) -> None:
    """Content-read path must stay token-gated after management relaxation."""
    session = _session_with_messages(db, [
        {"role": "user", "content": "q1"},
    ])
    with TestClient(app) as client:
        denied = client.get(f"/api/v1/prep/sessions/{session.id}/messages")
    assert denied.status_code == 403
    ok = client.get(
        f"/api/v1/prep/sessions/{session.id}/messages",
        headers=_headers(session),
    )
    assert ok.status_code == 200, ok.text


def test_fork_negative_up_to_keeps_everything(db) -> None:
    """Any negative up_to (not just -1) forks the full history."""
    session = _session_with_messages(db, [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ])
    with TestClient(app) as client:
        resp = client.post(
            f"/api/v1/prep/sessions/{session.id}/fork",
            json={"up_to": -2},
            headers=_headers(session),
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["message_count"] == 2
    db.expire_all()
    forked = db.get(PrepSession, resp.json()["id"])
    assert [m["content"] for m in json.loads(forked.messages)] == ["q1", "a1"]


def test_fork_clamps_huge_up_to_and_zeroes_counters(db) -> None:
    session = _session_with_messages(db, [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ])
    session.prompt_tokens = 111
    session.completion_tokens = 22
    session.cached_tokens = 5
    session.token_usage = 500
    session.linked_session_id = session.id
    db.commit()
    with TestClient(app) as client:
        resp = client.post(
            f"/api/v1/prep/sessions/{session.id}/fork",
            json={"up_to": 9999},
            headers=_headers(session),
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["message_count"] == 2
    db.expire_all()
    forked = db.get(PrepSession, resp.json()["id"])
    assert [m["content"] for m in json.loads(forked.messages)] == ["q1", "a1"]
    # Fresh branch accounting; linked context inherited.
    assert (forked.prompt_tokens, forked.completion_tokens) == (0, 0)
    assert (forked.cached_tokens, forked.token_usage) == (0, 0)
    assert forked.linked_session_id == session.id


def test_context_endpoint_reports_breakdown_and_usage(db) -> None:
    session = _session_with_messages(db, [
        {"role": "system", "content": "Coach instructions"},
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ])
    session.prompt_tokens = 100
    session.completion_tokens = 50
    session.cached_tokens = 10
    db.commit()
    with TestClient(app) as client:
        denied = client.get(f"/api/v1/prep/sessions/{session.id}/context")
        assert denied.status_code == 403
        resp = client.get(
            f"/api/v1/prep/sessions/{session.id}/context",
            headers=_headers(session),
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    keys = {b["key"] for b in body["buckets"]}
    assert {"user", "assistant", "system"} <= keys
    assert body["total_estimate"] == sum(b["tokens"] for b in body["buckets"])
    assert (body["prompt_tokens"], body["completion_tokens"], body["cached_tokens"]) == (100, 50, 10)


def test_compact_single_exchange_folds_whole(db, monkeypatch) -> None:
    """Single-exchange /compact is user-decided: it folds the whole exchange into an LLM summary."""
    from realmock.platform.capabilities.ai.llm.client import LLMClient

    class _SummaryLLM:
        context_window = 128000

        async def chat(self, messages, **kwargs):
            return "Session objectives: ship it"

    monkeypatch.setattr(LLMClient, "from_db", classmethod(lambda cls, *a, **k: _SummaryLLM()))
    session = _session_with_messages(db, [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ])
    with TestClient(app) as client:
        denied = client.post(f"/api/v1/prep/sessions/{session.id}/compact")
        assert denied.status_code == 403
        resp = client.post(
            f"/api/v1/prep/sessions/{session.id}/compact",
            headers={"Origin": "http://localhost:8080"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summarized"] is True
    # The exchange folds whole: summary block + working memory + language suffix
    # + context-usage suffix.
    assert body["message_count"] == 4
    db.expire_all()
    stored = json.loads(db.get(PrepSession, session.id).messages)
    assert str(stored[0]["content"]).startswith("[Conversation Minutes]")
    assert stored[1]["role"] == "system"
    assert str(stored[1]["content"]).startswith("[Working memory]")
    assert stored[2]["role"] == "system"
    assert str(stored[2]["content"]).startswith("[Reply language]")
    assert stored[3]["role"] == "system"
    assert str(stored[3]["content"]).startswith("[Context usage]")
