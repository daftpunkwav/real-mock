"""StepFun index HTTP tests for src/realmock/domains/interview/capabilities/rag/stepfun_index_http.py.

Covers: StepFunIndexHttp headers/pinned-client branches, create_vector_store
success/error/missing-id branches, unsafe-URL rejection, upload_kb_file/
attach_file/verify_vector_store branches (HTTP client faked).
Conventions: no real network/model downloads (all clients mocked).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def _stepfun_client():
    from realmock.domains.interview.capabilities.rag.stepfun_index_http import StepFunIndexHttp

    llm = SimpleNamespace(api_key="sk-test")
    settings = SimpleNamespace()
    return StepFunIndexHttp(llm, settings)


def test_stepfun_headers_and_client(monkeypatch) -> None:
    from realmock.domains.interview.capabilities.rag import stepfun_index_http as mod

    c = _stepfun_client()
    assert c._headers()["Authorization"] == "Bearer sk-test"
    captured = {}

    def _fake_pinned(api_base, allow_local=False, require_https=False, timeout=30.0):
        captured.update({"api_base": api_base, "allow_local": allow_local, "require_https": require_https})
        return SimpleNamespace()

    monkeypatch.setattr(mod, "make_pinned_async_client", _fake_pinned)
    monkeypatch.setattr(mod, "get_settings", lambda: SimpleNamespace(is_prod=True))
    c._pinned_client("https://api.example.com")
    assert captured["api_base"] == "https://api.example.com"
    assert captured["require_https"] is True


@pytest.mark.asyncio
async def test_stepfun_create_upload_attach_verify(monkeypatch) -> None:
    from realmock.domains.interview.capabilities.rag import stepfun_index_http as mod
    from realmock.platform.core.security import UnsafeURLError

    c = _stepfun_client()
    monkeypatch.setattr(mod, "is_safe_http_url", lambda url, allow_local=False: True)

    class _Resp:
        def __init__(self, status=200, payload=None):
            self.status_code = status
            self._payload = payload or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, resp, seen):
            self._resp = resp
            self._seen = seen

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None, data=None, files=None):
            self._seen.update({"url": url, "headers": headers, "json": json, "data": data, "files": files})
            return self._resp

        async def get(self, url, headers=None):
            self._seen.update({"url": url, "headers": headers})
            return self._resp

    # create success
    seen: dict = {}
    monkeypatch.setattr(c, "_pinned_client", lambda api_base: _Client(_Resp(200, {"id": "vs-1"}), seen))
    assert await c.create_vector_store("https://api.example.com", "k") == "vs-1"
    assert seen["url"].endswith("/vector_stores")

    # create http error propagates after warning
    monkeypatch.setattr(c, "_pinned_client", lambda api_base: _Client(_Resp(500, {"id": "x"}), {}))
    with pytest.raises(RuntimeError, match="http 500"):
        await c.create_vector_store("https://api.example.com", "k")

    # create missing id
    monkeypatch.setattr(c, "_pinned_client", lambda api_base: _Client(_Resp(200, {}), {}))
    with pytest.raises(RuntimeError, match="missing id"):
        await c.create_vector_store("https://api.example.com", "k")

    # unsafe url rejected
    monkeypatch.setattr(mod, "is_safe_http_url", lambda url, allow_local=False: False)
    with pytest.raises(UnsafeURLError):
        await c.create_vector_store("https://api.example.com", "k")
    with pytest.raises(UnsafeURLError):
        await c.upload_kb_file("https://api.example.com", "k", b"x")
    with pytest.raises(UnsafeURLError):
        await c.attach_file("https://api.example.com", "k", "vs", "f")
    with pytest.raises(UnsafeURLError):
        await c.verify_vector_store("https://api.example.com", "k", "vs")
    monkeypatch.setattr(mod, "is_safe_http_url", lambda url, allow_local=False: True)

    # upload + attach + verify
    seen2: dict = {}
    monkeypatch.setattr(c, "_pinned_client", lambda api_base: _Client(_Resp(200, {"id": "file-1"}), seen2))
    assert await c.upload_kb_file("https://api.example.com", "k", b"a") == "file-1"
    assert seen2["files"]["file"][0] == "company_kb.jsonl"
    with pytest.raises(RuntimeError, match="missing id"):
        monkeypatch.setattr(c, "_pinned_client", lambda api_base: _Client(_Resp(200, {}), {}))
        await c.upload_kb_file("https://api.example.com", "k", b"a")

    monkeypatch.setattr(c, "_pinned_client", lambda api_base: _Client(_Resp(200, {}), seen2))
    await c.attach_file("https://api.example.com", "k", "vs-1", "file-1")
    assert "vs-1" in seen2["url"]

    monkeypatch.setattr(c, "_pinned_client", lambda api_base: _Client(_Resp(200, {}), {}))
    await c.verify_vector_store("https://api.example.com", "k", "vs-1")
    monkeypatch.setattr(c, "_pinned_client", lambda api_base: _Client(_Resp(404, {}), {}))
    with pytest.raises(RuntimeError, match="does not exist"):
        await c.verify_vector_store("https://api.example.com", "k", "vs-missing")
