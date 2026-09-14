"""RAG backend using local Chroma + OpenAI-compatible ``/embeddings``.

Applicable to every LLM provider that exposes an OpenAI-compatible ``/embeddings`` endpoint
(OpenAI / DeepSeek / SiliconFlow / Moonshot / GLM / other compatible providers).

Implementation notes:

- Persistence dir resolved by _kb_data._data_dir() (DB-adjacent chroma dir; shared-data fallback).
"""

from __future__ import annotations

import logging
from typing import Any

from realmock.platform.config import Settings
from realmock.platform.core.constants import RAGBackendKind
from realmock.domains.interview.capabilities.rag._kb_data import COLLECTION_NAME, _build_documents, _data_dir
from realmock.platform.capabilities.ai.llm.client import LLMClient

logger = logging.getLogger(__name__)


class LocalEmbeddingRAG:
    """Local vector library + standard RAG implementation of remote embedding."""

    kind = RAGBackendKind.LOCAL

    def __init__(self, llm: LLMClient | None = None, settings: Settings | None = None):
        # ``chromadb`` is heavier during the import phase and is delayed until the first instantiation.
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self._llm = llm
        self._settings = settings
        self._client = chromadb.PersistentClient(
            path=str(_data_dir()),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def is_empty(self) -> bool:
        return self._collection.count() == 0

    async def build_index(self, force: bool = False) -> int:
        """Build (first time) or rebuild index. For :meth:`ensure_index` and test calls."""
        if force and self._collection.count() > 0:
            self._delete_all()
        if self._collection.count() > 0:
            logger.info("Local RAG index already exists, skip building")
            return self._collection.count()
        if self._llm is None:
            raise RuntimeError("Building a Local RAG index for the first time requires providing LLMClient for embed()")

        texts, metadatas, ids = _build_documents()
        logger.info("Build Local RAG index: %d documents", len(texts))
        embeddings = await self._llm.embed(texts)
        # The chromadb type annotation is stricter on the parameters of add and is compatible with list input at runtime.
        self._collection.add(
            documents=texts,
            embeddings=embeddings,  # type: ignore[arg-type]
            metadatas=metadatas,  # type: ignore[arg-type]
            ids=ids,
        )
        return len(texts)

    async def ensure_index(self) -> None:
        if self.is_empty():
            try:
                await self.build_index(force=False)
            except Exception as e:
                logger.warning("Local RAG index construction failed and will remain empty: %s", e)

    async def query(
        self,
        query_text: str,
        *,
        top_k: int = 3,
        company_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if self._collection.count() == 0:
            logger.warning("Local RAG index is empty, skip retrieval")
            return []
        if self._llm is None:
            raise RuntimeError("Local RAG retrieval requires LLMClient for query embedding")

        query_emb = (await self._llm.embed([query_text]))[0]
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_emb],
            "n_results": top_k,
        }
        if company_id:
            kwargs["where"] = {"company_id": company_id}

        result = self._collection.query(**kwargs)
        # chromadb return value is list[list[...]] package; compatible with None (default branch)
        documents = (result.get("documents") or [[]])[0] or []
        metadatas = (result.get("metadatas") or [[]])[0] or []
        distances = (result.get("distances") or [[]])[0] or []
        return [
            {
                "text": doc,
                "metadata": meta or {},
                "distance": dist,
            }
            for doc, meta, dist in zip(documents, metadatas, distances)
        ]

    async def query_for_company(
        self,
        query_text: str,
        company_id: str,
        *,
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        return await self.query(query_text, top_k=top_k, company_id=company_id)

    def _delete_all(self) -> None:
        try:
            self._client.delete_collection(COLLECTION_NAME)
        except Exception:
            logger.debug("Failed to delete RAG collection, continue to rebuild the collection", exc_info=True)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )


__all__ = ["LocalEmbeddingRAG"]