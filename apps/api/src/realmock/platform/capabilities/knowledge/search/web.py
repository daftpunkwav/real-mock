"""Network search tool (ddgs preferred, compatible with old package duckduckgo_search)."""

from __future__ import annotations

import logging
from typing import TypedDict

logger = logging.getLogger(__name__)


class SearchHit(TypedDict):
    """Search results can be displayed in a single bar (for front-end cards)."""

    title: str
    url: str
    snippet: str


def build_site_scoped_query(query: str, sites: list[str] | None = None) -> str:
    """Append ``site:`` filters to a query; return it unchanged when no sites are provided.

    Reused by resume evaluation, interview-experience search, etc.; the caller supplies the site list (see ``sites.py``).
    """
    q = (query or "").strip()
    if not q:
        return ""
    cleaned = [
        s.strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0]
        for s in (sites or [])
        if s and s.strip()
    ]
    if not cleaned:
        return q
    site_expr = " OR ".join(f"site:{s}" for s in cleaned)
    return f"({site_expr}) {q}"


def _normalize_hit(raw: dict) -> SearchHit | None:
    title = (raw.get("title") or "").strip()
    url = (raw.get("href") or raw.get("link") or "").strip()
    snippet = (raw.get("body") or raw.get("snippet") or "").strip()[:280]
    if not url:
        return None
    return {"title": title or url, "url": url, "snippet": snippet}


def _format_hits(hits: list[SearchHit]) -> str:
    if not hits:
        return "No relevant results found."
    lines: list[str] = []
    for i, h in enumerate(hits, start=1):
        lines.append(f"[{i}] {h['title']}\n    URL: {h['url']}\n    Snippet: {h['snippet']}")
    return "\n".join(lines)


# Bing is usually the most stable under domestic networks; do not put auto into the list to avoid being stuck in yandex and timeout for a long time
_DDGS_BACKENDS = ("bing", "duckduckgo")


def _search_with_ddgs(query: str, max_results: int) -> list[dict]:
    from ddgs import DDGS

    errors: list[str] = []
    with DDGS() as client:
        for backend in _DDGS_BACKENDS:
            try:
                results = list(
                    client.text(query, max_results=max_results, backend=backend)
                )
                if results:
                    return results
                errors.append(f"{backend}: empty")
            except Exception as e:
                errors.append(f"{backend}: {e}")
                logger.info("ddgs backend=%s failed: %s", backend, e)
    raise RuntimeError("; ".join(errors)[:400] or "no backend succeeded")


def _search_with_legacy(query: str, max_results: int) -> list[dict]:
    from duckduckgo_search import DDGS

    with DDGS() as client:
        return list(client.text(query, max_results=max_results))


def _unavailable(detail: str) -> str:
    return (
        "SEARCH_UNAVAILABLE\n"
        f"Search temporarily unavailable ({detail}).\n"
        "Do not invent result lists, links, or citation numbers; continue coaching "
        "with general knowledge and clearly tell the user it is based on general "
        "knowledge, not live search."
    )


def web_search_with_hits(
    query: str,
    max_results: int = 5,
    sites: list[str] | None = None,
) -> tuple[str, list[SearchHit]]:
    """Execute a search and return (text for the model, list of structured results).

    On failure, the text contains ``SEARCH_UNAVAILABLE`` and hits is empty.
    """
    final_query = build_site_scoped_query(query, sites)
    if not final_query:
        return "Empty query.", []

    errors: list[str] = []

    try:
        raw = _search_with_ddgs(final_query, max_results)
    except Exception as e:
        errors.append(f"ddgs: {e}")
        logger.warning("ddgs search failed, try old package: %s", e)
        try:
            raw = _search_with_legacy(final_query, max_results)
        except Exception as e2:
            errors.append(f"duckduckgo_search: {e2}")
            logger.warning("Old package search failed: %s", e2)
            return _unavailable(" | ".join(errors)[:400]), []

    hits: list[SearchHit] = []
    for r in raw[:max_results]:
        hit = _normalize_hit(r)
        if hit:
            hits.append(hit)
    return _format_hits(hits), hits


def web_search(
    query: str,
    max_results: int = 5,
    sites: list[str] | None = None,
) -> str:
    """Perform text search; ``sites`` is a non-empty time-limited domain name (reserved for Niuke/BOSS, etc.)."""
    text, _ = web_search_with_hits(query, max_results=max_results, sites=sites)
    return text
