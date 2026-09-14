"""RAG backend for StepFun-managed vector_stores.

The StepFun platform does not expose an ``/embeddings`` endpoint; instead, retrieval is a built-in
tool type in the OpenAI protocol:

.. code-block:: python

    tools = [{
        "type": "retrieval",
        "function": {
            "name": "company_kb",
            "description": "Company interview-style knowledge base",
            "options": {
                "vector_store_id": "1712...",
                "prompt_template": "Find content in the document {{knowledge}} that is relevant to {{query}}; if none exists, answer 'No relevant information'.",
            },
        },
    }]

The StepFun server automatically performs retrieval during the chat call and inserts relevant excerpts into the context,
so this backend is responsible for:

1. :meth:`ensure_index` — create / reuse the vector_store on StepFun and upload
   the built-in company knowledge-base document (skip this if the user supplied ``STEPFUN_VECTOR_STORE_ID``);
2. :meth:`query` — return an empty list; actual retrieval is performed by tools during chat;
3. :meth:`build_retrieval_tool` — emit an OpenAI-compatible tool definition
   for injection into the chat payload by :class:`realmock.domains.interview.services.interview.runner.InterviewRunner`.

Private HTTP methods (create/upload/attach/verify/pinned client) live in
:mod:`.stepfun_index_http`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from realmock.platform.config import Settings
from realmock.platform.core.constants import RAGBackendKind
from realmock.platform.core.security import (
    UnsafeURLError,
    assert_safe_http_url,
)
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.domains.interview.capabilities.rag._kb_data import _build_documents
from realmock.domains.interview.capabilities.rag.stepfun_index_http import StepFunIndexHttp

logger = logging.getLogger(__name__)


def _serialize_documents_to_jsonl() -> bytes:
    """Slice BUILTIN_COMPANIES into a JSONL byte stream consumable by StepFun.

    Each line is one JSON object; the ``text`` field contains the slice text, while ``metadata``
    carries ``company_id`` / ``company_name`` / ``section`` as filtering hints for retrieval
    on the StepFun server.
    """
    texts, metadatas, _ = _build_documents()
    lines: list[str] = []
    for text, meta in zip(texts, metadatas):
        lines.append(json.dumps({"text": text, "metadata": meta}, ensure_ascii=False))
    return ("\n".join(lines) + "\n").encode("utf-8")


class StepFunRetrievalRAG:
    """StepFun hosts the vector_stores backend."""

    kind = RAGBackendKind.STEPFUN

    def __init__(self, llm: LLMClient, settings: Settings):
        self._llm = llm
        self._settings = settings
        self._vector_store_id: str | None = settings.stepfun_vector_store_id
        self._ready: bool = bool(self._vector_store_id)
        self._index_http = StepFunIndexHttp(llm=llm, settings=settings)

    # ── Public API ──────────────────────────────────────

    def is_empty(self) -> bool:
        """The StepFun backend has no local index; when it is not ready, return True so the upper layer skips local retrieval.

        Actual retrieval is performed by the StepFun server during chat and is unrelated to this property.
        """
        return not self._ready

    async def ensure_index(self) -> None:
        """Ensure that a vector_store exists on StepFun and has the knowledge-base file attached.

        Flow:

        1. If ``STEPFUN_VECTOR_STORE_ID`` is configured → only verify that it exists;
        2. Otherwise, follow the official documentation:
           POST /vector_stores → POST /files (purpose=retrieval)
           → POST /vector_stores/{id}/files to attach it;
        3. On any failure, call ``logger.warning`` and do not raise (preserving the existing degradation policy).
        """
        api_base = self._settings.effective_embeddings_base  # StepFun usually shares its base with chat
        api_key = self._llm.api_key

        if not api_key:
            logger.warning("StepFun RAG skipped: API Key not configured")
            return

        try:
            assert_safe_http_url(api_base, allow_local=False)
        except UnsafeURLError as e:
            logger.warning("StepFun RAG skip: api_base is unsafe (%s)", e)
            return

        try:
            if self._vector_store_id:
                await self._index_http.verify_vector_store(api_base, api_key, self._vector_store_id)
                self._ready = True
                logger.info(
                    "StepFun vector_store is ready (reuse configuration): id=%s",
                    self._vector_store_id,
                )
                return

            vs_id = await self._index_http.create_vector_store(api_base, api_key)
            content = _serialize_documents_to_jsonl()
            file_id = await self._index_http.upload_kb_file(api_base, api_key, content)
            await self._index_http.attach_file(api_base, api_key, vs_id, file_id)
            self._vector_store_id = vs_id
            self._ready = True
            # Note: ID only is printed, file size is observable but not considered sensitive.
            logger.info(
                "StepFun vector_store was created successfully: id=%s file=%s",
                vs_id,
                file_id,
            )
        except Exception as e:
            logger.warning("StepFun RAG index build failed (remaining in RAG-less mode): %s", e)
            self._ready = False

    async def query(
        self,
        query_text: str,
        *,
        top_k: int = 3,
        company_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """The StepFun backend does not perform local retrieval directly; return an empty list.

        Actual retrieval is performed by the StepFun server during chat calls through ``tools[].type=retrieval``.
        This method still returns ``[]`` to satisfy the :class:`RAGBackend` protocol,
        allowing :class:`InterviewRunner` to use the common empty-``hits`` path in the RAG injection branch
        without a StepFun-specific check.
        """
        return []

    async def query_for_company(
        self,
        query_text: str,
        company_id: str,
        *,
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        return []

    # ── StepFun Retrieval Protocol Artifacts ───────────────────────────────

    def build_retrieval_tool(self) -> dict[str, Any] | None:
        """Generate an OpenAI-compatible retrieval tool definition.

        Returns:
            If ``vector_store_id`` is ready, return the tool dict; otherwise return ``None``
            (so the caller skips injection instead of injecting an invalid tool).
        """
        if not self._ready or not self._vector_store_id:
            return None
        return {
            "type": "retrieval",
            "function": {
                "name": "company_kb",
                "description": (
                    "Corporate interview style knowledge base. Including Byte, Tencent, Alibaba, Meituan, MiHoYo,"
                    "Interview styles, focus areas, typical questions and processes at OpenAI, Google and other companies."
                ),
                "options": {
                    "vector_store_id": self._vector_store_id,
                    "prompt_template": (
                        "Find content related to {{query}} from document {{knowledge}};"
                        "If the document does not have relevant answers, clearly state 'No relevant information'."
                    ),
                },
            },
        }


__all__ = ["StepFunRetrievalRAG"]
