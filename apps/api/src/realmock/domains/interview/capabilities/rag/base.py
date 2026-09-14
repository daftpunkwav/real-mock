"""Abstract interface for RAG backends.

Goal: when different LLM providers need distinct retrieval protocols, only implement
:class:`RAGBackend` and register it in the factory — callers stay unchanged.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from realmock.platform.core.constants import RAGBackendKind


@runtime_checkable
class RAGBackend(Protocol):
    """Unified interface for RAG backends.

    Query paths degrade to []/warnings; index-build may raise when LLM missing.
    """

    kind: RAGBackendKind

    async def ensure_index(self) -> None:
        """Make sure the index is ready. Try building in an empty library scenario, and only warn if it fails."""
        ...

    def is_empty(self) -> bool:
        """Whether the index is empty. The upper layer will skip retrieval when empty."""
        ...

    async def query(
        self,
        query_text: str,
        *,
        top_k: int = 3,
        company_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve the document fragments most relevant to the query.

        Returns:
            A list of dictionaries containing ``text`` / ``metadata`` / ``distance``;
            return ``[]`` when unavailable.
        """
        ...

    async def query_for_company(
        self,
        query_text: str,
        company_id: str,
        *,
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        """Limited company search."""
        ...


__all__ = ["RAGBackend"]