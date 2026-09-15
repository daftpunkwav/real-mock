"""Web search tests for apps/api/src/realmock/platform/capabilities/knowledge/search/web.py.

Covers: site-scoped query building, hit normalization/formatting and
web_search_with_hits with DDGS/legacy backends mocked.

Conventions: no real network (ddgs/legacy backends faked via monkeypatch); asyncio_mode=auto.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

from realmock.platform.capabilities.knowledge.search import web as web_mod


def test_build_site_scoped_query_variants() -> None:
    assert web_mod.build_site_scoped_query("", None) == ""
    assert web_mod.build_site_scoped_query("  ", ["a.com"]) == ""
    assert web_mod.build_site_scoped_query("q", None) == "q"
    assert web_mod.build_site_scoped_query("q", []) == "q"
    assert web_mod.build_site_scoped_query("q", ["  "]) == "q"
    assert web_mod.build_site_scoped_query("q", ["https://NowCoder.com/path ", "HTTP://a.COM"]) == (
        "(site:nowcoder.com OR site:a.com) q"
    )


def test_normalize_hit_missing_url() -> None:
    assert web_mod._normalize_hit({}) is None
    assert web_mod._normalize_hit({"title": "t"}) is None


def test_format_hits_empty_and_multi() -> None:
    assert web_mod._format_hits([]) == "No relevant results found."
    text = web_mod._format_hits(
        [
            {"title": "A", "url": "https://a.test", "snippet": "s1"},
            {"title": "B", "url": "https://b.test", "snippet": "s2"},
        ]
    )
    assert "[1] A" in text and "[2] B" in text


def test_unavailable_shape() -> None:
    text = web_mod._unavailable("boom")
    assert text.startswith("SEARCH_UNAVAILABLE")
    assert "boom" in text


def test_search_with_ddgs_first_backend_wins(monkeypatch) -> None:
    fake_client = MagicMock()
    fake_client.text.return_value = [{"href": "https://x.test", "title": "T", "body": "B"}]
    fake_ctx = MagicMock()
    fake_ctx.__enter__.return_value = fake_client
    fake_ctx.__exit__.return_value = False
    fake_mod = types.ModuleType("ddgs")
    fake_mod.DDGS = MagicMock(return_value=fake_ctx)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ddgs", fake_mod)
    out = web_mod._search_with_ddgs("q", 5)
    assert out[0]["href"] == "https://x.test"


def test_search_with_ddgs_falls_to_second_backend(monkeypatch) -> None:
    fake_client = MagicMock()
    fake_client.text.side_effect = [Exception("bing down"), [{"href": "https://y.test"}]]
    fake_ctx = MagicMock()
    fake_ctx.__enter__.return_value = fake_client
    fake_ctx.__exit__.return_value = False
    fake_mod = types.ModuleType("ddgs")
    fake_mod.DDGS = MagicMock(return_value=fake_ctx)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ddgs", fake_mod)
    out = web_mod._search_with_ddgs("q", 3)
    assert out[0]["href"] == "https://y.test"


def test_search_with_ddgs_empty_then_error(monkeypatch) -> None:
    import pytest as _pytest

    fake_client = MagicMock()
    fake_client.text.side_effect = [[], Exception("ddg down")]
    fake_ctx = MagicMock()
    fake_ctx.__enter__.return_value = fake_client
    fake_ctx.__exit__.return_value = False
    fake_mod = types.ModuleType("ddgs")
    fake_mod.DDGS = MagicMock(return_value=fake_ctx)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ddgs", fake_mod)
    with _pytest.raises(RuntimeError, match="bing"):
        web_mod._search_with_ddgs("q", 3)


def test_search_with_legacy(monkeypatch) -> None:
    fake_client = MagicMock()
    fake_client.text.return_value = [{"href": "https://z.test"}]
    fake_ctx = MagicMock()
    fake_ctx.__enter__.return_value = fake_client
    fake_ctx.__exit__.return_value = False
    fake_mod = types.ModuleType("duckduckgo_search")
    fake_mod.DDGS = MagicMock(return_value=fake_ctx)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "duckduckgo_search", fake_mod)
    assert web_mod._search_with_legacy("q", 2)[0]["href"] == "https://z.test"


def test_web_search_with_hits_empty_query() -> None:
    text, hits = web_mod.web_search_with_hits("   ")
    assert text == "Empty query."
    assert hits == []


def test_web_search_with_hits_ddgs_success(monkeypatch) -> None:
    monkeypatch.setattr(
        web_mod,
        "_search_with_ddgs",
        lambda q, mr: [
            {"title": "T", "href": "https://a.test", "body": "snip"},
            {"title": "no-url", "body": "x"},
        ],
    )
    text, hits = web_mod.web_search_with_hits("hello", max_results=5)
    assert len(hits) == 1
    assert hits[0]["url"] == "https://a.test"
    assert "[1]" in text


def test_web_search_with_hits_truncates_to_max(monkeypatch) -> None:
    monkeypatch.setattr(
        web_mod,
        "_search_with_ddgs",
        lambda q, mr: [{"href": f"https://a.test/{i}", "title": "t", "body": "b"} for i in range(10)],
    )
    _, hits = web_mod.web_search_with_hits("q", max_results=3)
    assert len(hits) == 3


def test_web_search_with_hits_fallback_legacy(monkeypatch) -> None:
    def _boom(q, mr):
        raise RuntimeError("ddgs down")

    monkeypatch.setattr(web_mod, "_search_with_ddgs", _boom)
    monkeypatch.setattr(
        web_mod, "_search_with_legacy", lambda q, mr: [{"href": "https://b.test", "title": "T"}]
    )
    text, hits = web_mod.web_search_with_hits("q")
    assert len(hits) == 1
    assert "No relevant" not in text


def test_web_search_with_hits_both_fail(monkeypatch) -> None:
    def _boom(q, mr):
        raise RuntimeError("ddgs down")

    def _boom2(q, mr):
        raise RuntimeError("legacy down")

    monkeypatch.setattr(web_mod, "_search_with_ddgs", _boom)
    monkeypatch.setattr(web_mod, "_search_with_legacy", _boom2)
    text, hits = web_mod.web_search_with_hits("q")
    assert hits == []
    assert text.startswith("SEARCH_UNAVAILABLE")


def test_web_search_wrapper(monkeypatch) -> None:
    monkeypatch.setattr(
        web_mod,
        "_search_with_ddgs",
        lambda q, mr: [{"href": "https://a.test", "title": "T", "body": "B"}],
    )
    assert "https://a.test" in web_mod.web_search("q")
