"""Company interview knowledge-base RAG.

Selects a backend implementation from settings.rag_backend during construction (local Chroma / stepfun / none);
with llm=None, degrades to an empty stub (for tests). Uses explicit delegation methods, with no __getattr__ magic.

Pure data/helper functions (_build_documents / _data_dir / format_context / COLLECTION_NAME)
live in :mod:`realmock.domains.interview.capabilities.rag._kb_data`.
"""

from __future__ import annotations

import logging
from typing import Any

from realmock.domains.interview.capabilities.rag._kb_data import COLLECTION_NAME, _build_documents, _data_dir, format_context
from realmock.domains.interview.capabilities.rag.factory import build_rag_backend

logger = logging.getLogger(__name__)


class _LegacyChromaStub:
    """Minimal placeholder implementation used by ``CompanyKnowledgeRAG(llm=None)`` (for tests)."""

    kind = None  # type: ignore[assignment]
    _llm = None
    _client = None
    _collection = None

    async def ensure_index(self) -> None:
        return None

    def is_empty(self) -> bool:
        if self._collection is None:
            return True
        return self._collection.count() == 0

    async def query(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    async def query_for_company(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []


class CompanyKnowledgeRAG:
    """Enterprise knowledge-base RAG (selects a backend from settings and delegates explicitly).

    The public methods ensure_index / is_empty / query / query_for_company delegate to
    the backend selected by the factory; when llm=None, they fall back to _LegacyChromaStub.
    """

    def __init__(self, llm: Any = None) -> None:
        if llm is None:
            self._impl: Any = _LegacyChromaStub()
        else:
            from realmock.platform.config import get_settings

            self._impl = build_rag_backend(llm=llm, settings=get_settings())

    @property
    def kind(self) -> Any:
        """Backend kind id (``local`` | ``stepfun`` | ``none``)."""
        return self._impl.kind

    async def ensure_index(self) -> None:
        """Build/refresh the company knowledge index (no-op when empty/disabled)."""
        await self._impl.ensure_index()

    def is_empty(self) -> bool:
        """Whether the knowledge index has no documents to retrieve."""
        return self._impl.is_empty()

    async def query(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        """Retrieve generic hits (backend-shaped ``query`` passthrough)."""
        return await self._impl.query(*args, **kwargs)

    async def query_for_company(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        """Retrieve hits scoped to one company (backend-shaped passthrough)."""
        return await self._impl.query_for_company(*args, **kwargs)


__all__ = [
    "CompanyKnowledgeRAG",
    "COLLECTION_NAME",
    "format_context",
    "_build_documents",
    "_data_dir",
]
