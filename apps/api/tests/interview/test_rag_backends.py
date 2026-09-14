"""Contract tests for the multi-backend RAG abstraction and the StepFun backend.

Design points:

- Do not make real HTTP requests; replace ``httpx.AsyncClient`` through ``monkeypatch`` to inspect
  whether the StepFun backend request URL / payload follows the official documented protocol;
- Verify the :func:`build_rag_backend` factory-selection logic;
- Verify that the :class:`CompanyKnowledgeRAG` wrapper continues to expose a stable API.
"""

from __future__ import annotations

import json
from typing import Any

from realmock.platform.config import Settings
from realmock.platform.core.constants import RAGBackendKind
from realmock.domains.interview.capabilities.rag.base import RAGBackend
from realmock.domains.interview.capabilities.rag.company_rag import CompanyKnowledgeRAG
from realmock.domains.interview.capabilities.rag.factory import _NullRAG, build_rag_backend
from realmock.domains.interview.capabilities.rag.local_backend import LocalEmbeddingRAG
from realmock.domains.interview.capabilities.rag.stepfun_backend import (
    StepFunRetrievalRAG,
    _serialize_documents_to_jsonl,
)
from tests.fakes import FakeLLMClient


# ── Factory selection ──────────────────────────────────────


def _make_settings(**overrides: Any) -> Settings:
    base = {
        "llm_api_base": "https://api.stepfun.com/v1",
        "llm_api_key": "sk-test",
        "llm_model": "step-3.7-flash",
        "rag_backend": "local",
    }
    base.update(overrides)
    return Settings(**base)


def test_factory_returns_local_embedding_rag_by_default() -> None:
    s = _make_settings()
    rag = build_rag_backend(llm=FakeLLMClient(), settings=s)
    assert isinstance(rag, RAGBackend)
    assert rag.kind == RAGBackendKind.LOCAL
    assert isinstance(rag, LocalEmbeddingRAG)


def test_factory_returns_stepfun_backend_when_configured() -> None:
    s = _make_settings(rag_backend="stepfun")
    rag = build_rag_backend(llm=FakeLLMClient(), settings=s)
    assert isinstance(rag, StepFunRetrievalRAG)
    assert rag.kind == RAGBackendKind.STEPFUN


def test_factory_returns_null_rag_when_disabled() -> None:
    s = _make_settings(rag_backend="none")
    rag = build_rag_backend(llm=FakeLLMClient(), settings=s)
    assert isinstance(rag, _NullRAG)
    assert rag.kind == RAGBackendKind.NONE
    assert rag.is_empty() is True


# ── LocalEmbeddingRAG contract ──────────────────────────────────────


def test_local_embedding_rag_satisfies_protocol(tmp_path, monkeypatch) -> None:
    """Use tmp_path to isolate the Chroma directory and verify that LocalEmbeddingRAG satisfies the RAGBackend protocol."""
    from realmock.domains.interview.capabilities.rag import _kb_data, local_backend

    # local_backend binds _data_dir from _kb_data, so both locations must be patched.
    monkeypatch.setattr(_kb_data, "_data_dir", lambda: tmp_path / "chroma")
    monkeypatch.setattr(local_backend, "_data_dir", lambda: tmp_path / "chroma")
    rag = LocalEmbeddingRAG(llm=FakeLLMClient(), settings=_make_settings())
    assert isinstance(rag, RAGBackend)
    assert rag.is_empty() is True
    assert rag.kind == RAGBackendKind.LOCAL


# ── StepFunRetrievalRAG ──────────────────────────────────────


def test_stepfun_rag_unready_tool_returns_none() -> None:
    """When vector_store is not ready, build_retrieval_tool must return None to avoid injecting an empty tool."""
    rag = StepFunRetrievalRAG(llm=FakeLLMClient(api_key="sk-test"), settings=_make_settings())
    assert rag.is_empty() is True
    assert rag.build_retrieval_tool() is None


def test_stepfun_rag_ready_tool_shape() -> None:
    rag = StepFunRetrievalRAG(llm=FakeLLMClient(api_key="sk-test"), settings=_make_settings())
    rag._vector_store_id = "171215831957549056"
    rag._ready = True
    tool = rag.build_retrieval_tool()
    assert tool is not None
    assert tool["type"] == "retrieval"
    assert tool["function"]["name"] == "company_kb"
    options = tool["function"]["options"]
    assert options["vector_store_id"] == "171215831957549056"
    assert "{{knowledge}}" in options["prompt_template"]
    assert "{{query}}" in options["prompt_template"]


def test_stepfun_rag_query_returns_empty_list() -> None:
    """The StepFun backend query must return []—the server performs the actual retrieval during chat."""
    rag = StepFunRetrievalRAG(llm=FakeLLMClient(api_key="sk-test"), settings=_make_settings())
    rag._ready = True
    rag._vector_store_id = "1712"
    # query/query_for_company should return an empty result (with no side effects for the caller).
    import asyncio

    async def _go() -> list[dict[str, Any]]:
        return await rag.query("anything", top_k=3, company_id="bytedance")

    hits = asyncio.run(_go())
    assert hits == []


def test_serialize_documents_to_jsonl_shape() -> None:
    """JSONL serialization must produce one JSON object per line with complete text/metadata fields."""
    raw = _serialize_documents_to_jsonl()
    lines = [ln for ln in raw.decode("utf-8").splitlines() if ln.strip()]
    assert len(lines) > 30
    for line in lines[:5]:
        obj = json.loads(line)
        assert "text" in obj and obj["text"]
        meta = obj["metadata"]
        assert meta.get("company_id")
        assert meta.get("section")


def test_stepfun_ensure_index_degrades_on_http_failure(monkeypatch) -> None:
    """ensure_index should only warn when the HTTP call fails and must not raise."""
    import httpx

    rag = StepFunRetrievalRAG(llm=FakeLLMClient(api_key="sk-test"), settings=_make_settings())

    class _Boom:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **kw):
            raise RuntimeError("network down")

        async def get(self, *a, **kw):
            raise RuntimeError("network down")

    monkeypatch.setattr(httpx, "AsyncClient", _Boom)
    import asyncio

    async def _go() -> None:
        await rag.ensure_index()

    asyncio.run(_go())
    assert rag.is_empty() is True
    assert rag._ready is False


def test_stepfun_ensure_index_uses_configured_vector_store_id(monkeypatch) -> None:
    """If settings already provides STEPFUN_VECTOR_STORE_ID, perform only GET validation and do not create one."""
    import httpx

    captured: dict[str, Any] = {"calls": []}

    class _StubResp:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {"id": "1712", "name": "kb"}

        def raise_for_status(self) -> None:
            return None

    class _StubClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kw):
            captured["calls"].append(("GET", url))
            return _StubResp()

        async def post(self, url, **kw):
            captured["calls"].append(("POST", url))
            return _StubResp()

    # Focus on the HTTP sequence: allow URL validation (real DNS results differ across environments),
    # make_pinned_async_client also performs real DNS resolution internally, so replace it as well.
    # (The HTTP layer has moved to stepfun_index_http, and both validation and pin are in that module;
    #  The assert_safe_http_url call at the ensure_index entry point remains in stepfun_backend.)
    from realmock.domains.interview.capabilities.rag import stepfun_backend as sb
    from realmock.domains.interview.capabilities.rag import stepfun_index_http as shttp

    monkeypatch.setattr(sb, "assert_safe_http_url", lambda *a, **kw: None)
    monkeypatch.setattr(shttp, "is_safe_http_url", lambda *a, **kw: True)
    monkeypatch.setattr(shttp, "make_pinned_async_client", lambda *a, **kw: _StubClient())
    monkeypatch.setattr(httpx, "AsyncClient", _StubClient)

    settings = _make_settings(
        rag_backend="stepfun",
        stepfun_vector_store_id="171215831957549056",
    )
    rag = StepFunRetrievalRAG(llm=FakeLLMClient(api_key="sk-test"), settings=settings)
    import asyncio

    asyncio.run(rag.ensure_index())
    # Should trigger exactly one GET (existence check) and no POST (creation)
    methods = [m for m, _ in captured["calls"]]
    assert "GET" in methods
    assert "POST" not in methods
    assert rag._ready is True


# ── CompanyKnowledgeRAG wrapper ──────────────────────────────────────


def test_company_knowledge_rag_wrapper_delegates_kind() -> None:
    """The wrapper should pass kind through to the internal impl."""
    rag = CompanyKnowledgeRAG(llm=FakeLLMClient())
    assert rag.kind == RAGBackendKind.LOCAL


def test_company_knowledge_rag_wrapper_legacy_when_no_llm() -> None:
    rag = CompanyKnowledgeRAG(llm=None)
    assert rag.kind is None
    assert rag.is_empty() is True
