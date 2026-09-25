"""HTTP layer for the StepFun vector_stores index: create / upload / attach / verify.

Split from :mod:`...stepfun_backend`. Handles only requests to create, upload to, attach files to, and verify
the StepFun-managed index; it does not touch the protocol surface (``query`` / ``build_retrieval_tool``). All outbound traffic uses
:func:`make_pinned_async_client` (DNS pinning), never a bare ``httpx.AsyncClient``.
"""

from __future__ import annotations

import asyncio

import logging
from typing import Any

import httpx

from realmock.platform.core.security import (
    UnsafeURLError,
    is_safe_http_url,
    make_pinned_async_client,
    redact_api_key,
)
from realmock.platform.config import get_settings

logger = logging.getLogger(__name__)

_STEPFUN_FILE_NAME = "company_kb.jsonl"
_STEPFUN_VS_NAME = "company_kb"
_STEPFUN_REQUEST_TIMEOUT = 30.0


class StepFunIndexHttp:
    """StepFun HTTP client for hosted indexing (stateless, request orchestration only)."""

    def __init__(self, llm: Any, settings: Any):
        self._llm = llm
        self._settings = settings

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._llm.api_key}",
            "Content-Type": "application/json",
        }

    def _pinned_client(self, api_base: str) -> httpx.AsyncClient:
        """Consistent with LLM client: outbound DNS pin, mitigate rebinding TOCTOU."""
        return make_pinned_async_client(
            api_base,
            allow_local=False,
            require_https=bool(get_settings().is_prod),
            timeout=_STEPFUN_REQUEST_TIMEOUT,
        )

    async def create_vector_store(self, api_base: str, api_key: str) -> str:
        """POST /vector_stores → return vector_store_id."""
        url = f"{api_base}/vector_stores"
        # Double SSRF verification: defensive programming, even if ensure_index is verified.
        if not is_safe_http_url(url, allow_local=False):
            raise UnsafeURLError(f"StepFun URL rejected: {url}")
        payload = {"name": _STEPFUN_VS_NAME}
        # Keep DNS resolution off the event loop (same convention as web_fetch).
        pinned = await asyncio.to_thread(self._pinned_client, api_base)
        async with pinned as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            if resp.status_code >= 400:
                logger.warning(
                    "StepFun create vector_store failed: status=%s key=%s",
                    resp.status_code,
                    redact_api_key(api_key),
                )
            resp.raise_for_status()
            data = resp.json()
        vs_id = str(data.get("id") or "").strip()
        if not vs_id:
            raise RuntimeError("StepFun vector_store create response missing id field")
        return vs_id

    async def upload_kb_file(
        self,
        api_base: str,
        api_key: str,
        content: bytes,
    ) -> str:
        """POST /files (purpose=retrieval) → return file_id."""
        url = f"{api_base}/files"
        if not is_safe_http_url(url, allow_local=False):
            raise UnsafeURLError(f"StepFun URL rejected: {url}")
        files = {"file": (_STEPFUN_FILE_NAME, content, "application/jsonl")}
        data = {"purpose": "retrieval"}
        headers = {"Authorization": f"Bearer {api_key}"}
        # Keep DNS resolution off the event loop (same convention as web_fetch).
        pinned = await asyncio.to_thread(self._pinned_client, api_base)
        async with pinned as client:
            resp = await client.post(url, headers=headers, data=data, files=files)
            resp.raise_for_status()
            payload = resp.json()
        file_id = str(payload.get("id") or "").strip()
        if not file_id:
            raise RuntimeError("StepFun files upload response is missing id field")
        return file_id

    async def attach_file(
        self,
        api_base: str,
        api_key: str,
        vector_store_id: str,
        file_id: str,
    ) -> None:
        """POST /vector_stores/{id}/files associated files."""
        url = f"{api_base}/vector_stores/{vector_store_id}/files"
        if not is_safe_http_url(url, allow_local=False):
            raise UnsafeURLError(f"StepFun URL rejected: {url}")
        payload = {"file_ids": file_id}
        # Keep DNS resolution off the event loop (same convention as web_fetch).
        pinned = await asyncio.to_thread(self._pinned_client, api_base)
        async with pinned as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            resp.raise_for_status()

    async def verify_vector_store(
        self,
        api_base: str,
        api_key: str,
        vector_store_id: str,
    ) -> None:
        """Lightweight GET /vector_stores/{id} check for ID existence. On failure, clear it and wait for the next rebuild."""
        url = f"{api_base}/vector_stores/{vector_store_id}"
        if not is_safe_http_url(url, allow_local=False):
            raise UnsafeURLError(f"StepFun URL rejected: {url}")
        # Keep DNS resolution off the event loop (same convention as web_fetch).
        pinned = await asyncio.to_thread(self._pinned_client, api_base)
        async with pinned as client:
            resp = await client.get(url, headers=self._headers())
            if resp.status_code == 404:
                raise RuntimeError(f"StepFun vector_store does not exist: id={vector_store_id}")
            resp.raise_for_status()
