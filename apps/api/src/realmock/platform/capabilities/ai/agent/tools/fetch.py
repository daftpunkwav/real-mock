"""Reusable public-web page fetch tool for Agents.

Complements :mod:`search`: the agent can search for sources, then fetch one
to read the actual content. Output is plain text extracted from the HTML,
hard-capped. Reuses the platform URL-safety layer for SSRF mitigation.

Failure is honest: the observation says FETCH_FAILED and explicitly tells
the model not to invent page content.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any

import httpx

from realmock.platform.capabilities.ai.agent.tools.spec import ToolSpec
from realmock.platform.core.security.url import UnsafeURLError, is_safe_http_url
from realmock.platform.core.security.url_pin import make_pinned_async_client

FETCH_DEFAULT_MAX_CHARS = 6_000
FETCH_HARD_MAX_CHARS = 12_000
FETCH_TIMEOUT_SECONDS = 15.0

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Block-level tags whose absence of whitespace between siblings glues words.
_TAG_GLUE = re.compile(r"<(script|style|noscript)[\s\S]*?</\1>", re.IGNORECASE)
_ANY_TAG = re.compile(r"<[^>]+>")
_SCRIPT_SHADOW = re.compile(r"<(script|style|noscript)\b", re.IGNORECASE)
_TITLE = re.compile(r"<title[^>]*>([\s\S]*?)</title>", re.IGNORECASE)
_META_CHARSET = re.compile(
    r"<meta[^>]+charset=['\"]?([^'\"\s>]+)", re.IGNORECASE
)


def _detect_charset(html_bytes: bytes, header_charset: str | None) -> str:
    """Pick a decoding charset from the HTTP header or a meta tag."""
    if header_charset:
        return header_charset
    # Sniff the first few KB for a meta charset declaration.
    head = html_bytes[:4096].decode("ascii", errors="ignore")
    match = _META_CHARSET.search(head)
    if match:
        return match.group(1).strip()
    return "utf-8"


def _strip_html(raw_html: str) -> str:
    """Extract readable text from an HTML document (no external deps)."""
    text = _TAG_GLUE.sub(" ", raw_html)
    # An unclosed script/style would otherwise leak its body as text.
    shadow = _SCRIPT_SHADOW.search(text)
    if shadow is not None:
        text = text[: shadow.start()]
    text = _ANY_TAG.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _unavailable(detail: str) -> str:
    return (
        "FETCH_FAILED\n"
        f"Could not fetch the page ({detail}).\n"
        "Do not invent the page's content; rely on the search snippet or "
        "general knowledge, and say so."
    )


def _header_charset(content_type: str | None) -> str | None:
    if not content_type:
        return None
    # Case-insensitive "charset=xxx" in Content-Type.
    match = re.search(r"charset=['\"]?([^'\"\s;]+)", content_type, re.IGNORECASE)
    return match.group(1).strip() if match else None


async def _fetch_page(url: str, max_chars: int) -> str:
    """Fetch one safe URL and return its readable text as a JSON payload."""
    if not is_safe_http_url(url, allow_local=True):
        raise UnsafeURLError("URL failed platform SSRF policy")
    async with make_pinned_async_client(
        url,
        allow_local=True,
        timeout=FETCH_TIMEOUT_SECONDS,
    ) as client:
        response = await client.get(
            url,
            headers={"User-Agent": _USER_AGENT, "Accept": "text/html,*/*;q=0.8"},
        )
        response.raise_for_status()
        raw = await response.aread()
    charset = _detect_charset(raw, _header_charset(response.headers.get("content-type")))
    html_text = raw.decode(charset, errors="replace")
    text = _strip_html(html_text)
    if not text:
        return _unavailable("no readable text (page is empty or script-only)")
    title = ""
    title_match = _TITLE.search(html_text)
    if title_match is not None:
        title = re.sub(r"\s+", " ", html.unescape(title_match.group(1))).strip()[:200]
    return json.dumps(
        {"url": url, "title": title, "text": text[:max_chars]},
        ensure_ascii=False,
    )


def clamp_max_chars(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = FETCH_DEFAULT_MAX_CHARS
    return max(500, min(value, FETCH_HARD_MAX_CHARS))


async def execute_web_fetch(args: dict[str, Any]) -> str:
    """Fetch one public web page and return its readable text (JSON payload)."""
    url = str(args.get("url") or "").strip()
    if not url:
        return json.dumps({"error": "empty_url"}, ensure_ascii=False)
    if not url.lower().startswith(("http://", "https://")):
        return _unavailable("only http/https URLs are supported")
    max_chars = clamp_max_chars(args.get("max_chars"))
    try:
        return await _fetch_page(url, max_chars)
    except UnsafeURLError as e:
        return _unavailable(f"URL blocked by policy: {e}")
    except Exception as e:
        return _unavailable(f"{type(e).__name__}: {str(e)[:200]}")


def web_fetch_tool_spec() -> ToolSpec:
    """Build the ``web_fetch`` tool spec (read one page found via web_search)."""

    async def handler(args: dict[str, Any]) -> str:
        return await execute_web_fetch(args or {})

    return ToolSpec(
        name="web_fetch",
        description=(
            "Fetch ONE public web page found via web_search and read its actual "
            "content (first characters of the readable text). Use it to verify a "
            "claim or quote a source accurately; do not guess page contents "
            "without fetching."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Absolute http(s) URL to fetch"},
                "max_chars": {
                    "type": "integer",
                    "description": (
                        f"Readable-text characters to return, default "
                        f"{FETCH_DEFAULT_MAX_CHARS}, maximum {FETCH_HARD_MAX_CHARS}"
                    ),
                },
            },
            "required": ["url"],
        },
        handler=handler,
    )


__all__ = [
    "FETCH_DEFAULT_MAX_CHARS",
    "FETCH_HARD_MAX_CHARS",
    "clamp_max_chars",
    "execute_web_fetch",
    "web_fetch_tool_spec",
]
