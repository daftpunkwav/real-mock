"""GitHub REST API client (thin wrapper).

Calls api.github.com directly without depending on the official MCP transport layer, with semantics aligned to common GitHub MCP tools.
Without a configured token, it uses the unauthenticated quota (about 60 requests/hour); with a token, the quota rises to 5,000 requests/hour.

The HTTP layer (constants and ``_get`` error mapping) lives in :mod:`.github_http`;
REST resource method implementations live in :mod:`.rest_ops`; this module retains only the class, initialization, and thin delegation.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx  # noqa: F401 - keep the module-level reference: tests patch client.httpx.AsyncClient

from realmock.platform.config import get_settings

from .github_http import async_get
from .token_store import read_stored_token
from .rest_ops import (
    _get_file_content,
    _get_languages,
    _get_readme,
    _get_repo,
    _get_tree,
    _get_user,
    _list_commits,
    _list_issues,
    _list_pull_requests,
    _list_repos,
)

logger = logging.getLogger(__name__)


class GitHubClient:
    """Lightweight GitHub REST client."""

    def __init__(self, token: str | None = None):
        settings = get_settings()
        # Explicit argument wins (tests, one-off probes); otherwise the stored
        # Settings credential; otherwise the process env fallback. The client
        # never distinguishes sources — callers see one authenticated quota.
        self.token = (token if token is not None else read_stored_token() or settings.github_token) or ""
        self._headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mock-agent-tools/1.0",
        }
        if self.token:
            self._headers["Authorization"] = f"Bearer {self.token}"

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await async_get(path, headers=self._headers, params=params)

    # ── REST resource method (see rest_ops for implementation)──────────────

    async def get_rate_limit(self) -> dict[str, Any]:
        return await self._get("/rate_limit")

    async def get_user(self, username: str) -> dict[str, Any]:
        return await _get_user(self, username)

    async def list_repos(
        self,
        username: str,
        *,
        sort: str = "updated",
        per_page: int = 10,
    ) -> dict[str, Any]:
        return await _list_repos(self, username, sort=sort, per_page=per_page)

    async def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        return await _get_repo(self, owner, repo)

    async def get_tree(
        self,
        owner: str,
        repo: str,
        *,
        branch: str,
        recursive: bool = True,
    ) -> dict[str, Any]:
        return await _get_tree(self, owner, repo, branch=branch, recursive=recursive)

    async def get_readme(self, owner: str, repo: str) -> dict[str, Any]:
        return await _get_readme(self, owner, repo)

    async def list_commits(
        self,
        owner: str,
        repo: str,
        *,
        per_page: int = 10,
        author: str | None = None,
    ) -> dict[str, Any]:
        return await _list_commits(self, owner, repo, per_page=per_page, author=author)

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "all",
        per_page: int = 10,
    ) -> dict[str, Any]:
        return await _list_pull_requests(self, owner, repo, state=state, per_page=per_page)

    async def list_issues(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "all",
        per_page: int = 10,
    ) -> dict[str, Any]:
        return await _list_issues(self, owner, repo, state=state, per_page=per_page)

    async def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        *,
        ref: str | None = None,
    ) -> dict[str, Any]:
        return await _get_file_content(self, owner, repo, path, ref=ref)

    async def get_languages(self, owner: str, repo: str) -> dict[str, Any]:
        return await _get_languages(self, owner, repo)
