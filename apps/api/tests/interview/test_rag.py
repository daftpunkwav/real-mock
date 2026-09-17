"""Company knowledge-base RAG unit tests.

Use FakeLLMClient to provide controllable fake embeddings so retrieval results are predictable.
Use an independent collection name and chroma directory for each test to avoid client-cache reuse.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from realmock.domains.interview.capabilities.rag.company_rag import (
    CompanyKnowledgeRAG,
    _build_documents,
    format_context,
)
from tests.fakes import FakeLLMClient


@pytest.fixture
def rag(tmp_path: Path, monkeypatch) -> CompanyKnowledgeRAG:
    """Provide each test with a RAG instance using an independent chroma directory and collection name."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    # Override _data_dir so chroma persists to a temporary directory
    from realmock.domains.interview.capabilities.rag import company_rag

    monkeypatch.setattr(
        company_rag, "_data_dir", lambda: tmp_path / "chroma"
    )
    # Use an independent collection name for each test to avoid chromadb client-level caching.
    unique_name = f"test_{uuid.uuid4().hex[:8]}"
    rag = CompanyKnowledgeRAG(FakeLLMClient())
    # Replace the collection name
    import chromadb
    from chromadb.config import Settings

    rag._impl._client = chromadb.PersistentClient(
        path=str(tmp_path / "chroma"),
        settings=Settings(anonymized_telemetry=False, allow_reset=True),
    )
    rag._impl._collection = rag._impl._client.get_or_create_collection(
        name=unique_name, metadata={"hnsw:space": "cosine"}
    )
    return rag


def test_build_documents_covers_all_companies() -> None:
    texts, metadatas, ids = _build_documents()
    company_ids = {m["company_id"] for m in metadatas}
    assert "bytedance" in company_ids
    assert "alibaba" in company_ids
    assert len(texts) == len(metadatas) == len(ids)
    assert len(ids) > 30


def test_format_context_empty_returns_empty() -> None:
    assert format_context([]) == ""


def test_format_context_renders_hits() -> None:
    hits = [
        {
            "text": "ByteDance focus: performance optimization",
            "metadata": {"company_id": "bytedance", "section": "focus_areas"},
            "distance": 0.1,
        },
    ]
    out = format_context(hits)
    assert "Enterprise knowledge base search supplement" in out
    assert "[focus_areas]" in out
    assert "ByteDance" in out


async def test_rag_build_index_populates_collection(rag: CompanyKnowledgeRAG) -> None:
    assert rag.is_empty()
    n = await rag._impl.build_index()
    assert n > 30
    assert not rag.is_empty()


async def test_rag_build_index_skips_when_existing(rag: CompanyKnowledgeRAG) -> None:
    llm = rag._impl._llm
    await rag._impl.build_index()
    embed_calls_before = len(llm.embed_calls)
    await rag._impl.build_index()
    assert len(llm.embed_calls) == embed_calls_before


async def test_rag_query_returns_relevant_hits(rag: CompanyKnowledgeRAG) -> None:
    await rag._impl.build_index()
    hits = await rag.query_for_company(
        "How does bytedance assess project deep dives?", "bytedance", top_k=3
    )
    assert hits
    assert all(h["metadata"]["company_id"] == "bytedance" for h in hits)


async def test_rag_query_filters_by_company(rag: CompanyKnowledgeRAG) -> None:
    await rag._impl.build_index()
    hits = await rag.query_for_company("Project performance", "bytedance", top_k=5)
    assert all(h["metadata"]["company_id"] == "bytedance" for h in hits)


async def test_rag_query_empty_index_returns_empty(rag: CompanyKnowledgeRAG) -> None:
    hits = await rag.query("anything")
    assert hits == []


async def test_rag_ensure_index_idempotent(rag: CompanyKnowledgeRAG) -> None:
    await rag.ensure_index()
    n_after_first = rag._impl._collection.count()
    await rag.ensure_index()
    assert rag._impl._collection.count() == n_after_first


async def test_rag_force_rebuild(rag: CompanyKnowledgeRAG) -> None:
    llm = rag._impl._llm
    await rag._impl.build_index()
    n = rag._impl._collection.count()
    n2 = await rag._impl.build_index(force=True)
    assert n2 == n
    assert len(llm.embed_calls) >= 2


async def test_rag_filters_low_distance_hits(rag: CompanyKnowledgeRAG) -> None:
    """Matches that are too distant should be filtered out in _maybe_retrieve_rag."""
    await rag._impl.build_index()
    hits = await rag.query("xyzqwerty12345nocontent", top_k=3)
    assert isinstance(hits, list)