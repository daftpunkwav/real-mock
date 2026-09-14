"""Interview service startup declarations and standalone-run hooks.

Declares the interview session-domain for the composition root to register;
the bootstrap call itself lives in the entry points (``main`` / ``asgi``),
never in this package. System-insights provider is wired only from the
composition root (``asgi``) so this package never imports the growth domain.
"""

from __future__ import annotations

import logging

from realmock.platform.database import ApiSessionLocal

logger = logging.getLogger(__name__)

# Session-domain ORM the composition root registers for standalone runs.
SESSION_DOMAINS: tuple[str, ...] = ("interview",)


def wire_session_catalog() -> None:
    """Register interview catalog for standalone runs (no growth imports)."""
    from realmock.domains.interview.services.catalog import register_interview_session_catalog

    register_interview_session_catalog()


async def ensure_rag_index() -> None:
    """Build company RAG index on first start (failure does not block boot)."""
    import os

    if os.environ.get("TEST_MODE") == "1":
        return
    try:
        from realmock.domains.interview.capabilities.rag.company_rag import CompanyKnowledgeRAG
        from realmock.platform.capabilities.ai.llm.client import LLMClient

        db = ApiSessionLocal()
        try:
            llm = LLMClient.from_db(db)
            api_key = getattr(llm, "api_key", None)
            if not api_key:
                logger.info("LLM API Key is not configured, skipping RAG index building")
                return
            rag = CompanyKnowledgeRAG(llm)
            await rag.ensure_index()
        finally:
            try:
                db.close()
            except Exception:
                logger.debug("RAG startup ApiSessionLocal close failed", exc_info=True)
    except Exception as e:
        logger.warning("RAG index build failed (startup continues): %s", e)
