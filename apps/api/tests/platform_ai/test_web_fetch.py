"""web_fetch tool: HTML-to-text extraction, redirects, clamps, charset, honest failure contract."""

from __future__ import annotations

import asyncio
import json

import httpx

from realmock.platform.capabilities.ai.agent.tools import fetch as fetch_mod
from realmock.platform.capabilities.ai.agent.tools.fetch import (
    FETCH_ALLOWED_PORTS,
    _detect_charset,
    _read_capped,
    clamp_max_chars,
    execute_web_fetch,
    web_fetch_tool_spec,
)
from realmock.platform.capabilities.ai.agent.tools.fetch import _strip_html


def test_strip_html_removes_tags_script_and_collapses_space():
    html = (
        "<html><head><title>FastAPI Guide</title></head><body>"
        "<h1>Intro</h1><p>FastAPI  is  fast.</p>"
        "<script>var x = 'should not leak';</script>"
        "<style>.a{color:red}</style></body></html>"
    )
    text = _strip_html(html)
    assert "FastAPI is fast." in text
    assert "should not leak" not in text
    assert "color:red" not in text
    assert "<" not in text


def test_clamp_max_chars_bounds():
    assert clamp_max_chars(None) == 6000
    assert clamp_max_chars(1) == 500
    assert clamp_max_chars(999_999) == 12_000


def test_execute_rejects_empty_and_non_http_urls():
    empty = asyncio.run(execute_web_fetch({}))
    assert json.loads(empty)["error"] == "empty_url"

    ftp = asyncio.run(execute_web_fetch({"url": "ftp://example.com/x"}))
    assert "FETCH_FAILED" in ftp
    assert "http/https" in ftp


def test_execute_failure_is_honest_not_invented():
    result = asyncio.run(execute_web_fetch({"url": "https://realmock.invalid.example/x"}))
    assert "FETCH_FAILED" in result
    assert "Do not invent" in result


def test_spec_shape():
    spec = web_fetch_tool_spec()
    assert spec.name == "web_fetch"
    assert spec.parameters["required"] == ["url"]
    assert "web_search" in spec.description


# ---- redirect hops ---------------------------------------------------------------


class _FakeResponse:
    """Minimal httpx.Response stand-in for streamed fetches."""

    def __init__(self, status: int, *, location: str | None = None,
                 content_type: str | None = "text/html", body: bytes = b"") -> None:
        self.status_code = status
        self.headers = {}
        if location is not None:
            self.headers["location"] = location
        if content_type is not None:
            self.headers["content-type"] = content_type
        self._body = body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"status {self.status_code}",
                request=httpx.Request("GET", "https://example.invalid/"),
                response=httpx.Response(self.status_code),
            )

    async def aiter_bytes(self):
        if self._body:
            yield self._body


class _FakeStream:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _FakeResponse:
        return self._response

    async def __aexit__(self, *exc) -> bool:
        return False


class _FakeClient:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = responses

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    def stream(self, method: str, url: str, headers: dict | None = None) -> _FakeStream:
        del method, url, headers
        return _FakeStream(self._responses.pop(0))


def _patch_clients(monkeypatch, responses: list[_FakeResponse]) -> list[tuple[str, frozenset]]:
    """Route every pinned-client creation to queued fake responses."""
    created: list[tuple[str, frozenset]] = []

    def fake_factory(url: str, **kwargs):
        created.append((url, kwargs.get("allowed_ports")))
        return _FakeClient([responses.pop(0)])

    monkeypatch.setattr(fetch_mod, "make_pinned_async_client", fake_factory)
    return created


_PAGE = b"<html><head><title>Final</title></head><body><p>Landing content.</p></body></html>"


def test_redirects_are_followed_hop_by_hop(monkeypatch) -> None:
    """Each hop gets its own pinned client, so policy checks re-run per hop."""
    created = _patch_clients(monkeypatch, [
        _FakeResponse(302, location="https://cdn.example/b"),          # hop 1
        _FakeResponse(200, body=_PAGE),                                # hop 2
    ])
    payload = json.loads(asyncio.run(execute_web_fetch({"url": "https://start.example/a"})))
    assert [url for url, _ in created] == ["https://start.example/a", "https://cdn.example/b"]
    assert payload["url"] == "https://cdn.example/b"  # the page actually read
    assert "Landing content." in payload["text"]
    # The outbound port discipline travels with every hop.
    assert all(ports == FETCH_ALLOWED_PORTS for _, ports in created)


def test_relative_redirect_target_is_resolved(monkeypatch) -> None:
    created = _patch_clients(monkeypatch, [
        _FakeResponse(301, location="final"),  # relative Location
        _FakeResponse(200, body=_PAGE),
    ])
    asyncio.run(execute_web_fetch({"url": "https://start.example/a"}))
    assert created[1][0] == "https://start.example/final"


def test_redirect_without_location_fails_honestly(monkeypatch) -> None:
    _patch_clients(monkeypatch, [_FakeResponse(302)])
    result = asyncio.run(execute_web_fetch({"url": "https://start.example/a"}))
    assert "FETCH_FAILED" in result
    assert "Location" in result


def test_redirect_loop_is_capped(monkeypatch) -> None:
    _patch_clients(monkeypatch, [_FakeResponse(302, location="/loop")] * 10)
    result = asyncio.run(execute_web_fetch({"url": "https://start.example/loop"}))
    assert "FETCH_FAILED" in result
    assert "too many redirects" in result


# ---- download cap + charset ------------------------------------------------------


def test_read_capped_stops_at_cap():
    class _Chunked:
        async def aiter_bytes(self):
            for _ in range(100):
                yield b"a" * 100

    assert len(asyncio.run(_read_capped(_Chunked(), 250))) == 250


def test_detect_charset_validates_codec_names():
    """Unknown charset names must fall back instead of killing the decode."""
    assert _detect_charset(b"", "not-a-real-codec") == "utf-8"
    assert _detect_charset(b"", "gbk") == "gbk"
    assert _detect_charset(b"<meta charset='gb18030'>", None) == "gb18030"
    assert _detect_charset(b"<meta charset='bogus'>", None) == "utf-8"
    # Header wins when it names a real codec.
    assert _detect_charset(b"<meta charset='gbk'>", "utf-8") == "utf-8"
