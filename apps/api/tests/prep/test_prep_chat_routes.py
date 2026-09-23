"""Chat route tests for realmock.domains.prep.routes.chat.

Covers: _build_prep_llm, _turn_policy, prep_message, prep_message_stream, get_prep_messages, get_prep_context and their HTTP wrappers
Conventions: No real LLM/network; LLM and PrepAgent faked via monkeypatch; rate limits reset per test
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

def _session(db, **kwargs) -> PrepSession:
    kwargs.setdefault("status", "active")
    kwargs.setdefault("messages", "[]")
    kwargs.setdefault("access_token", new_access_token())
    row = PrepSession(**kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

class _FakeLLM:
    def __init__(self) -> None:
        self.model = "test-model"
        self.context_window = 8000

def _patch_llm(monkeypatch, fake=None):
    import realmock.domains.prep.routes.chat as chat_route

    fake = fake or _FakeLLM()

    def _fake_from_db(api_db, *, profile_id=None, reasoning_effort=None):
        _fake_from_db.captured = {"profile_id": profile_id, "reasoning_effort": reasoning_effort}
        return fake

    _fake_from_db.captured = {}  # type: ignore[attr-defined]
    monkeypatch.setattr(chat_route.LLMClient, "from_db", staticmethod(_fake_from_db))
    return fake, _fake_from_db

class _FakeAgent:
    def __init__(self, reply="hello-reply") -> None:
        self.context_window = 8000
        self.last_prompt_estimate = 11
        self.last_message_count = 3
        self.last_turn_id = "t1"
        self.last_prefix_fingerprint = "fp1"
        self._reply = reply
        self.chat_kwargs = None

    async def chat(self, *args, **kwargs):
        self.chat_kwargs = kwargs
        return self._reply

    async def chat_stream(self, *args, **kwargs):  # pragma: no cover - replaced per-test
        yield "x"

def _patch_agent(monkeypatch, agent=None):
    import realmock.domains.prep.routes.chat as chat_route

    agent = agent or _FakeAgent()
    monkeypatch.setattr(chat_route, "PrepAgent", lambda session, llm: agent)
    return agent

def test_build_prep_llm_forwards_overrides(monkeypatch) -> None:
    import realmock.domains.prep.routes.chat as chat_route
    from realmock.domains.prep.schemas import PrepMessageRequest

    _, factory = _patch_llm(monkeypatch)
    body = PrepMessageRequest(content="hi", model_profile_id=7, reasoning_effort="high")
    chat_route._build_prep_llm(object(), body)  # type: ignore[arg-type]
    assert factory.captured == {"profile_id": 7, "reasoning_effort": "high"}

def test_turn_policy_resolves() -> None:
    import realmock.domains.prep.routes.chat as chat_route
    from realmock.domains.prep.schemas import PrepMessageRequest

    opts = chat_route._turn_policy(PrepMessageRequest(content="hi"))
    assert opts.intensity == "balanced"
    opts2 = chat_route._turn_policy(
        PrepMessageRequest(content="hi", compact_intensity="light", compact_retain=3)
    )
    assert opts2.intensity == "light"
    assert opts2.retain == 3

@pytest.mark.asyncio
async def test_prep_message_missing_is_a3001(db) -> None:
    import realmock.domains.prep.routes.chat as chat_route
    from realmock.domains.prep.schemas import PrepMessageRequest
    from realmock.platform.core.errors import ApiBusinessError

    with pytest.raises(ApiBusinessError) as exc:
        await chat_route.prep_message(999999, PrepMessageRequest(content="hi"), db, db, "tok")
    assert exc.value.error_code == "A3001"

@pytest.mark.asyncio
async def test_prep_message_forbidden_and_completed(db, monkeypatch) -> None:
    import realmock.domains.prep.routes.chat as chat_route
    from realmock.domains.prep.schemas import PrepMessageRequest
    from realmock.platform.core.errors import ApiBusinessError

    row = _session(db)
    with pytest.raises(ApiBusinessError) as exc:
        await chat_route.prep_message(row.id, PrepMessageRequest(content="hi"), db, db, "wrong")
    assert exc.value.error_code == "A0401"

    row.status = "completed"
    db.commit()
    with pytest.raises(ApiBusinessError) as exc2:
        await chat_route.prep_message(row.id, PrepMessageRequest(content="hi"), db, db, row.access_token)
    assert exc2.value.error_code == "A3002"

@pytest.mark.asyncio
async def test_prep_message_success_returns_totals(db, monkeypatch) -> None:
    import realmock.domains.prep.routes.chat as chat_route
    from realmock.domains.prep.schemas import PrepMessageRequest

    row = _session(
        db, token_usage=5, prompt_tokens=10, completion_tokens=20, cached_tokens=1
    )
    _patch_llm(monkeypatch)
    agent = _patch_agent(monkeypatch, _FakeAgent(reply="done-reply"))
    out = await chat_route.prep_message(
        row.id,
        PrepMessageRequest(content="hi", drop_last_assistant=True, ui_locale="en"),
        db,
        db,
        row.access_token,
    )
    assert out.reply == "done-reply"
    assert out.token_usage == 5
    assert out.prompt_tokens == 10
    assert out.prompt_tokens_estimated == 11
    assert out.message_count == 3
    assert agent.chat_kwargs is not None
    assert agent.chat_kwargs["drop_last_assistant"] is True

@pytest.mark.asyncio
async def test_prep_message_stream_guards(db) -> None:
    import realmock.domains.prep.routes.chat as chat_route
    from realmock.domains.prep.schemas import PrepMessageRequest
    from realmock.platform.core.errors import ApiBusinessError

    class _Req:
        async def is_disconnected(self) -> bool:
            return False

    with pytest.raises(ApiBusinessError) as exc:
        await chat_route.prep_message_stream(999999, PrepMessageRequest(content="hi"), _Req(), db, db, "t")  # type: ignore[arg-type]
    assert exc.value.error_code == "A3001"

    row = _session(db)
    with pytest.raises(ApiBusinessError) as exc2:
        await chat_route.prep_message_stream(row.id, PrepMessageRequest(content="hi"), _Req(), db, db, "bad")  # type: ignore[arg-type]
    assert exc2.value.error_code == "A0401"

    row.status = "completed"
    db.commit()
    with pytest.raises(ApiBusinessError) as exc3:
        await chat_route.prep_message_stream(row.id, PrepMessageRequest(content="hi"), _Req(), db, db, row.access_token)  # type: ignore[arg-type]
    assert exc3.value.error_code == "A3002"

@pytest.mark.asyncio
async def test_prep_message_stream_dict_str_and_done(db, monkeypatch) -> None:
    import realmock.domains.prep.routes.chat as chat_route
    from realmock.domains.prep.schemas import PrepMessageRequest

    row = _session(db, token_usage=9, prompt_tokens=1, completion_tokens=2, cached_tokens=3)
    _patch_llm(monkeypatch)

    class _Agent(_FakeAgent):
        async def chat_stream(self, *args, **kwargs):
            yield {"type": "search_results", "groups": []}
            yield {"content": "bare-dict-no-type"}
            yield "plain-token"

    agent = _Agent()
    monkeypatch.setattr(chat_route, "PrepAgent", lambda session, llm: agent)

    class _Req:
        async def is_disconnected(self) -> bool:
            return False

    resp = await chat_route.prep_message_stream(
        row.id, PrepMessageRequest(content="hi"), _Req(), db, db, row.access_token  # type: ignore[arg-type]
    )
    body = b""
    async for chunk in resp.body_iterator:
        body += chunk if isinstance(chunk, bytes) else str(chunk).encode()
    text = body.decode()
    assert '"type": "search_results"' in text
    assert '"type": "token"' in text
    assert "bare-dict-no-type" in text
    assert "plain-token" in text
    assert '"type": "done"' in text
    assert '"token_usage": 9' in text

@pytest.mark.asyncio
async def test_prep_message_stream_disconnect_breaks(db, monkeypatch) -> None:
    import realmock.domains.prep.routes.chat as chat_route
    from realmock.domains.prep.schemas import PrepMessageRequest

    row = _session(db)
    _patch_llm(monkeypatch)

    seen = {"n": 0}

    class _Agent(_FakeAgent):
        async def chat_stream(self, *args, **kwargs):
            seen["n"] += 1
            yield "tok1"
            yield "tok2-never"

    monkeypatch.setattr(chat_route, "PrepAgent", lambda session, llm: _Agent())

    class _Req:
        calls = 0

        async def is_disconnected(self) -> bool:
            type(self).calls += 1
            return type(self).calls >= 2

    _Req.calls = 0
    resp = await chat_route.prep_message_stream(
        row.id, PrepMessageRequest(content="hi"), _Req(), db, db, row.access_token  # type: ignore[arg-type]
    )
    body = b""
    async for chunk in resp.body_iterator:
        body += chunk if isinstance(chunk, bytes) else str(chunk).encode()
    assert "tok1" in body.decode()
    assert "tok2-never" not in body.decode()

@pytest.mark.asyncio
async def test_prep_message_stream_error_is_redacted(db, monkeypatch) -> None:
    import realmock.domains.prep.routes.chat as chat_route
    from realmock.domains.prep.schemas import PrepMessageRequest

    row = _session(db)
    _patch_llm(monkeypatch)

    class _Agent(_FakeAgent):
        async def chat_stream(self, *args, **kwargs):
            raise RuntimeError("sk-secret-boom")
            yield "unreachable"  # pragma: no cover

    monkeypatch.setattr(chat_route, "PrepAgent", lambda session, llm: _Agent())

    class _Req:
        async def is_disconnected(self) -> bool:
            return False

    resp = await chat_route.prep_message_stream(
        row.id, PrepMessageRequest(content="hi"), _Req(), db, db, row.access_token  # type: ignore[arg-type]
    )
    body = b""
    async for chunk in resp.body_iterator:
        body += chunk if isinstance(chunk, bytes) else str(chunk).encode()
    text = body.decode()
    # Upstream errors surface verbatim (credential-redacted), not as generic copy.
    assert "sk-s***boom" in text
    assert "sk-secret-boom" not in text

@pytest.mark.asyncio
async def test_get_prep_messages_edges(db) -> None:
    import realmock.domains.prep.routes.chat as chat_route
    from realmock.platform.core.errors import ApiBusinessError

    with pytest.raises(ApiBusinessError) as exc:
        chat_route.get_prep_messages(999999, db, "t")
    assert exc.value.error_code == "A3001"

    row = _session(db)
    with pytest.raises(ApiBusinessError):
        chat_route.get_prep_messages(row.id, db, "bad")

    row.messages = json.dumps(
        [
            {"role": "assistant", "content": "ok <|im_start|>leak"},
            "plain-string-row",
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
            {"role": "user", "content": "hello"},
        ]
    )
    db.commit()
    out = chat_route.get_prep_messages(row.id, db, row.access_token)
    assert len(out) == 3
    assert "<|im_start|>" not in out[0].content
    assert out[1].content == ""
    assert out[2].content == "hello"

@pytest.mark.asyncio
async def test_get_prep_context_edges(db) -> None:
    import realmock.domains.prep.routes.chat as chat_route
    from realmock.platform.core.errors import ApiBusinessError

    with pytest.raises(ApiBusinessError) as exc:
        chat_route.get_prep_context(999999, db, "t")
    assert exc.value.error_code == "A3001"

    row = _session(
        db,
        messages=json.dumps([{"role": "user", "content": "hello world"}]),
        prompt_tokens=4,
        completion_tokens=5,
        cached_tokens=6,
    )
    with pytest.raises(ApiBusinessError):
        chat_route.get_prep_context(row.id, db, "bad")
    out = chat_route.get_prep_context(row.id, db, row.access_token)
    assert out.total_estimate >= 0
    assert len(out.buckets) > 0
    assert out.prompt_tokens == 4
    assert out.completion_tokens == 5
    assert out.cached_tokens == 6

def test_prep_message_http_success(db, monkeypatch) -> None:
    row = _session(db)
    _patch_llm(monkeypatch)
    _patch_agent(monkeypatch, _FakeAgent(reply="http-ok"))
    with TestClient(app) as client:
        denied = client.post(f"/api/v1/prep/sessions/{row.id}/message", json={"content": "hi"})
        assert denied.status_code == 403
        resp = client.post(
            f"/api/v1/prep/sessions/{row.id}/message",
            json={"content": "hi"},
            headers={"X-Interview-Token": row.access_token},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["reply"] == "http-ok"

def test_prep_stream_http_error_redacted(db, monkeypatch) -> None:
    row = _session(db)
    _patch_llm(monkeypatch)

    class _Agent(_FakeAgent):
        async def chat_stream(self, *args, **kwargs):
            raise RuntimeError("upstream-secret")
            yield "x"  # pragma: no cover

    _patch_agent(monkeypatch, _Agent())
    with TestClient(app) as client:
        with client.stream(
            "POST",
            f"/api/v1/prep/sessions/{row.id}/message/stream",
            json={"content": "hi"},
            headers={"X-Interview-Token": row.access_token},
        ) as resp:
            assert resp.status_code == 200
            body = "".join(resp.iter_text())
    # Upstream failures surface verbatim (credential-redacted), never generic copy.
    assert "upstream-secret" in body
