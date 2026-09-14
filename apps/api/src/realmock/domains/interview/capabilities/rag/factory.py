"""RAG backend factory and ``none`` placeholder implementation.

Read the ``rag_backend`` field from :class:`realmock.platform.config.Settings`, then select and construct
the corresponding backend. To add a backend: implement the :class:`RAGBackend` protocol → add
one branch to ``build_rag_backend``; callers need no changes.
"""

from __future__ import annotations

import logging
from typing import Any

from realmock.platform.config import Settings
from realmock.platform.core.constants import RAGBackendKind
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.domains.interview.capabilities.rag.base import RAGBackend

logger = logging.getLogger(__name__)


class _NullRAG:
    """Placeholder implementation for ``RAGBackendKind.NONE``.

    All methods degrade safely: ``ensure_index`` is a no-op, ``is_empty`` is always True,
    and ``query`` always returns ``[]``. This makes it easy to disable the enterprise knowledge base in production or during debugging.
    """

    kind = RAGBackendKind.NONE

    async def ensure_index(self) -> None:  # noqa: D401
        return None

    def is_empty(self) -> bool:
        return True

    async def query(
        self,
        query_text: str,
        *,
        top_k: int = 3,
        company_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return []

    async def query_for_company(
        self,
        query_text: str,
        company_id: str,
        *,
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        return []


def build_rag_backend(llm: LLMClient, settings: Settings) -> RAGBackend:
    """Select a backend implementation according to ``settings.rag_backend``.

    Args:
        llm: BYOK LLM client; the backend reuses its credentials as needed.
        settings: Application configuration containing ``rag_backend`` / ``stepfun_vector_store_id`` etc.

    Returns:
        Any implementation of the :class:`RAGBackend` protocol.
    """
    kind = settings.rag_backend

    if kind == RAGBackendKind.NONE:
        logger.info("RAG backend = none, Enterprise Knowledge Base retrieval is off")
        return _NullRAG()

    if kind == RAGBackendKind.STEPFUN:
        # Delayed import: avoid stepfun_backend strong dependencies from being loaded even when not in use.
        from realmock.domains.interview.capabilities.rag.stepfun_backend import StepFunRetrievalRAG

        logger.info("RAG backend = stepfun(StepFun managed vector_stores)")
        return StepFunRetrievalRAG(llm=llm, settings=settings)

    # Default: native Chroma + OpenAI compatible /embeddings
    from realmock.domains.interview.capabilities.rag.local_backend import LocalEmbeddingRAG

    logger.info("RAG backend = local (local Chroma + /embeddings)")
    return LocalEmbeddingRAG(llm=llm, settings=settings)


__all__ = ["build_rag_backend"]