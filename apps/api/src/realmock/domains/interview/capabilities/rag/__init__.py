"""Aggregated exports for RAG submodules.

External code imports through this module to avoid directly importing internal file paths in multiple places:

- :class:`RAGBackend` —— backend protocol
- :func:`build_rag_backend` —— backend factory
- :class:`CompanyKnowledgeRAG` —— backward-compatible wrapper (preserves the legacy API)
- :func:`format_context` —— hit fragments → Chinese context fragment (backend-independent)
"""

from realmock.domains.interview.capabilities.rag.base import RAGBackend
from realmock.domains.interview.capabilities.rag.company_rag import (
    COLLECTION_NAME,
    CompanyKnowledgeRAG,
    format_context,
)
from realmock.domains.interview.capabilities.rag.factory import build_rag_backend

__all__ = [
    "RAGBackend",
    "build_rag_backend",
    "CompanyKnowledgeRAG",
    "format_context",
    "COLLECTION_NAME",
]