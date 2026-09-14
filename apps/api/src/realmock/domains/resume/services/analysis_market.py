"""Market search orchestration: plan queries, fetch web context, cache it.

Responsibilities:
- Fetch job-market snippets for planned queries (open web + job-board scope)
- Cache market context in-process by resume-text hash

Keyword inference lives in ``market_keywords``; query planning lives in
``market_queries`` (both re-exported here so existing callers and tests keep
a stable import path). Never invent a canned job title such as
"software engineer".

Search language follows the resume body (CJK → zh-CN queries, else en),
not the analysis UI locale. Cache is per-process (lost on restart, not
shared across workers). Query/cache caps live in ``schemas.limits``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import OrderedDict

from realmock.domains.resume.schemas.limits import (
    MARKET_CACHE_MAX,
    MARKET_SEARCH_HITS_PER_QUERY,
)
from realmock.domains.resume.services.market_keywords import (
    infer_resume_query_locale,
    infer_search_keywords,
    infer_target_role_from_resume,
)
from realmock.domains.resume.services.market_queries import (
    default_market_queries,
    generate_market_queries,
    market_query_planning_instruction,
)
from realmock.domains.resume.services.sites import RESUME_MARKET_SEARCH_SITES
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.models import Resume

logger = logging.getLogger(__name__)

_MARKET_CACHE: OrderedDict[str, tuple[str, list[str]]] = OrderedDict()


async def get_market_context_cached(
    r: Resume, llm: LLMClient
) -> tuple[str, list[str]]:
    """Cache market context by a hash of the resume content.

    Return ``(market_ctx, search_queries)``. The resume-review Agent prefers
    live ``web_search`` tools; this cache remains for callers that still
    pre-fetch market text.
    """
    key = hashlib.sha1((r.raw_text or "").encode("utf-8")).hexdigest()[:16]
    cached = _MARKET_CACHE.get(key)
    if cached is not None:
        _MARKET_CACHE.move_to_end(key)
        return cached
    queries, _customized = await generate_market_queries(r, llm)
    market_ctx, search_queries = await gather_resume_market_context(r, queries)
    _MARKET_CACHE[key] = (market_ctx, search_queries)
    while len(_MARKET_CACHE) > MARKET_CACHE_MAX:
        _MARKET_CACHE.popitem(last=False)
    return market_ctx, search_queries


async def gather_resume_market_context(
    r: Resume, queries: list[str]
) -> tuple[str, list[str]]:
    """Retrieve job-market snippets for given queries.

    Open-web search always runs. Configured job-board domains are merged in
    as extra unique hits so site filters cannot empty the result set.
    ``search_queries`` only contains queries that actually returned evidence,
    so downstream audit fields are not polluted by failed fetches.

    Args:
        r: Source resume (kept for signature compatibility; unused — only
            ``queries`` drive retrieval).
        queries: Search queries to run (one open-web + one job-board fetch each).

    Returns:
        ``(market_context_text, evidenced_queries)``.
    """
    del r
    from realmock.platform.capabilities.knowledge.search.web import web_search_with_hits

    sites = list(RESUME_MARKET_SEARCH_SITES) or None
    hits_n = MARKET_SEARCH_HITS_PER_QUERY

    async def _one(q: str) -> tuple[str, str]:
        def _run() -> tuple[str, str]:
            text, hits = web_search_with_hits(q, hits_n)
            lines = [f"[Open web]\nQuery: {q}", text]
            seen = {h["url"] for h in hits}
            if sites:
                board_text, board_hits = web_search_with_hits(q, hits_n, sites=sites)
                extra = [h for h in board_hits if h["url"] not in seen]
                if extra:
                    lines.append("[Job-board scoped]\n" + board_text)
                    hits = list(hits) + extra
            for h in hits[:hits_n]:
                lines.append(f"- {h['title']} ({h['url']})")
            return q, "\n".join(lines)

        return await asyncio.to_thread(_run)

    if not queries:
        return "", []

    results = await asyncio.gather(
        *(_one(q) for q in queries), return_exceptions=True
    )
    blocks: list[str] = []
    used: list[str] = []
    for q, res in zip(queries, results):
        if isinstance(res, BaseException):
            logger.warning("Market search failed q=%s: %s", q, res)
            continue
        used.append(q)
        blocks.append(res[1])
    return "\n\n".join(blocks), used


__all__ = [
    "default_market_queries",
    "gather_resume_market_context",
    "generate_market_queries",
    "get_market_context_cached",
    "infer_resume_query_locale",
    "infer_search_keywords",
    "infer_target_role_from_resume",
    "market_query_planning_instruction",
]
