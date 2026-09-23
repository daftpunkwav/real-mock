"""Reusable public-web page fetch tool for Agents.

Complements :mod:`search`: the agent can search for sources, then fetch one
to read the actual content. Output is plain text extracted from the HTML,
hard-capped. Reuses the platform URL-safety layer for SSRF mitigation, and
follows redirects hop-by-hop so every hop passes the same policy checks.

Failure is honest: the observation says FETCH_FAILED and explicitly tells
the model not to invent page content.
"""

from __future__ import annotations

import asyncio
import codecs
import html
import json
import re
from typing import Any
from urllib.parse import urljoin

import httpx

from realmock.platform.capabilities.ai.agent.tools.spec import ToolSpec
from realmock.platform.core.security.url import UnsafeURLError
from realmock.platform.core.security.url_pin import make_pinned_async_client

FETCH_DEFAULT_MAX_CHARS = 6_000
FETCH_HARD_MAX_CHARS = 12_000
FETCH_TIMEOUT_SECONDS = 15.0
#: Ports a public page fetch may target. Enforced even for loopback hosts so a
#: prompt-injected URL cannot probe local services on arbitrary ports.
FETCH_ALLOWED_PORTS = frozenset({80, 443})

#: Redirect hops followed (each hop is re-validated and re-pinned), and the cap.
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECT_HOPS = 5
#: Meta-charset sniff window: declarations live in the document head.
_META_SNIFF_BYTES = 4096

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Block-level tags whose absence of whitespace between siblings glues words.
_TAG_GLUE = re.compile(r"<(script|style|noscript)[\s\S]*?</\1>", re.IGNORECASE)
_ANY_TAG = re.compile(r"<[^>]+>")
_SCRIPT_SHADOW = re.compile(r"<(script|style|noscript)\b", re.IGNORECASE)
_TITLE = re.compile(r"<title[^>]*>([\s\S]*?)</title>", re.IGNORECASE)
#: Charset declaration in a meta tag; the value is restricted to codec-name
#: characters, and _detect_charset still validates it via codecs.lookup.
_META_CHARSET = re.compile(
    r"<meta[^>]+charset\s*=\s*['\"]?([A-Za-z0-9._-]+)", re.IGNORECASE
)


def _meta_charset(html_bytes: bytes) -> str | None:
    """Charset declared by a ``<meta>`` tag in the document head, if any."""
    head = html_bytes[:_META_SNIFF_BYTES].decode("ascii", errors="ignore")
    match = _META_CHARSET.search(head)
    return match.group(1).strip() if match else None


def _detect_charset(html_bytes: bytes, header_charset: str | None) -> str:
    """Pick a decodable charset from the HTTP header or a meta tag.

    Unknown codec names (mis-declared pages) are skipped instead of raising
    ``LookupError`` out of the decode below.
    """
    for candidate in (header_charset, _meta_charset(html_bytes)):
        if not candidate:
            continue
        try:
            codecs.lookup(candidate)
        except LookupError:
            continue
        return candidate
    return "utf-8"


async def _read_capped(response: httpx.Response, cap: int) -> bytes:
    """Read at most ``cap`` body bytes (a huge page must not balloon memory)."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        chunks.append(chunk)
        total += len(chunk)
        if total >= cap:
            break
    return b"".join(chunks)[:cap]


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
    """Fetch one safe URL (following redirects hop-by-hop) as a JSON payload.

    Every hop goes through :func:`make_pinned_async_client`, so the SSRF
    policy and DNS pinning apply to the redirect target as well — never only
    to the URL the model supplied.
    """
    cap = max(max_chars * 4, _META_SNIFF_BYTES)
    current = url
    hops = 0
    raw = b""
    content_type: str | None = None
    while True:
        if hops > _MAX_REDIRECT_HOPS:
            return _unavailable(f"too many redirects (>{_MAX_REDIRECT_HOPS})")
        # Policy validation and DNS pinning both resolve DNS; keep them off
        # the event loop so a slow resolver cannot stall every stream.
        # Loopback stays blocked: this tool fetches public pages, and the
        # model must not be able to drive loopback management endpoints.
        client = await asyncio.to_thread(
            make_pinned_async_client,
            current,
            allow_local=False,
            allowed_ports=FETCH_ALLOWED_PORTS,
            timeout=FETCH_TIMEOUT_SECONDS,
        )
        async with client:
            async with client.stream(
                "GET",
                current,
                headers={"User-Agent": _USER_AGENT, "Accept": "text/html,*/*;q=0.8"},
            ) as response:
                if response.status_code in _REDIRECT_STATUSES:
                    location = response.headers.get("location")
                    if not location:
                        return _unavailable(
                            "redirect without a Location header "
                            f"(status {response.status_code})"
                        )
                    current = urljoin(current, location)
                    hops += 1
                    continue
                response.raise_for_status()
                raw = await _read_capped(response, cap)
                content_type = response.headers.get("content-type")
        break
    charset = _detect_charset(raw, _header_charset(content_type))
    html_text = raw.decode(charset, errors="replace")
    text = _strip_html(html_text)
    if not text:
        return _unavailable("no readable text (page is empty or script-only)")
    title = ""
    title_match = _TITLE.search(html_text)
    if title_match is not None:
        title = re.sub(r"\s+", " ", html.unescape(title_match.group(1))).strip()[:200]
    return json.dumps(
        {"url": current, "title": title, "text": text[:max_chars]},
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
        timeout_seconds=45.0,
    )


__all__ = [
    "FETCH_ALLOWED_PORTS",
    "FETCH_DEFAULT_MAX_CHARS",
    "FETCH_HARD_MAX_CHARS",
    "clamp_max_chars",
    "execute_web_fetch",
    "web_fetch_tool_spec",
]
