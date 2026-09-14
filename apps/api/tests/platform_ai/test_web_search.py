"""Unit test for structured web_search results (does not make a real network request)."""

from realmock.platform.capabilities.knowledge.search.web import _format_hits, _normalize_hit, build_site_scoped_query


def test_normalize_hit_prefers_href_and_body():
    hit = _normalize_hit(
        {"title": "Interview notes", "href": "https://example.com/a", "body": "Summary content"}
    )
    assert hit == {
        "title": "Interview notes",
        "url": "https://example.com/a",
        "snippet": "Summary content",
    }


def test_normalize_hit_falls_back_link_snippet():
    hit = _normalize_hit(
        {"title": "", "link": "https://example.com/b", "snippet": "x" * 300}
    )
    assert hit is not None
    assert hit["title"] == "https://example.com/b"
    assert hit["url"] == "https://example.com/b"
    assert len(hit["snippet"]) == 280


def test_normalize_hit_skips_missing_url():
    assert _normalize_hit({"title": "No link", "body": "…"}) is None


def test_format_hits_empty():
    assert _format_hits([]) == "No relevant results found."


def test_format_hits_list():
    text = _format_hits(
        [{"title": "T", "url": "https://x.test", "snippet": "S"}]
    )
    assert "[1] T" in text
    assert "URL: https://x.test" in text
    assert "Snippet: S" in text


def test_site_scoped_query():
    assert build_site_scoped_query("agent interview notes", ["nowcoder.com"]) == (
        "(site:nowcoder.com) agent interview notes"
    )
    assert build_site_scoped_query("  ", None) == ""
