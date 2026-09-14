"""web_fetch tool: HTML-to-text extraction, clamps, honest failure contract."""

from __future__ import annotations

import asyncio
import json

from realmock.platform.capabilities.ai.agent.tools.fetch import (
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
