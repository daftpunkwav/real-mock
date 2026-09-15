"""Memory service tests for realmock.domains.prep.services.memories.

Covers: clean_tags, clean_reasons, _decode_list, create/list/find branches
Conventions: Temp DB only; no network; rate limits reset per test
"""
from __future__ import annotations
import json
import pytest
from realmock.domains.prep.models import PrepMemory

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()

def _make_memory(db, **kwargs) -> PrepMemory:
    from realmock.domains.prep.services import create_memory

    kwargs.setdefault("summary", "seed summary")
    return create_memory(db, **kwargs)

def test_clean_tags_caps_at_twenty() -> None:
    from realmock.domains.prep.services.memories import clean_tags

    tags = clean_tags([f"t{i}" for i in range(30)])
    assert len(tags) == 20
    assert tags[0] == "t0"
    dupes = clean_tags(["a", "a", " b ", "", None, 123])
    assert dupes == ["a", "b", "123"]

def test_clean_reasons_caps_at_ten() -> None:
    from realmock.domains.prep.services.memories import clean_reasons

    reasons = clean_reasons([f"r{i}" for i in range(15)])
    assert len(reasons) == 10

def test_decode_list_invalid_json() -> None:
    from realmock.domains.prep.services.memories import _decode_list

    assert _decode_list("not-json{{{") == []
    assert _decode_list('{"a": 1}') == []
    assert _decode_list('["a", 1]') == ["a", "1"]

def test_create_memory_invalid_score(db) -> None:
    from realmock.domains.prep.services.memories import create_memory

    with pytest.raises(ValueError, match="1..10"):
        create_memory(db, summary="bad", score=99)
    with pytest.raises(ValueError, match="1..10"):
        create_memory(db, summary="bad", score=0)

def test_list_memories_tag_filter(db) -> None:
    from realmock.domains.prep.services.memories import list_memories

    _make_memory(db, summary="tag-a", tags=["alpha", "common"])
    _make_memory(db, summary="tag-b", tags=["beta", "common"])
    only_alpha = list_memories(db, tag="alpha", limit=10)
    assert all("alpha" in json.loads(r.tags) for r in only_alpha)
    assert list_memories(db, tag="missing-xyz", limit=10) == []
    limited = list_memories(db, limit=1)
    assert len(limited) == 1

def test_find_memory_by_summary_empty(db) -> None:
    from realmock.domains.prep.services.memories import find_memory_by_summary

    assert find_memory_by_summary(db, "") is None
    assert find_memory_by_summary(db, "   ") is None
    row = _make_memory(db, summary="unique-find-me")
    found = find_memory_by_summary(db, "unique-find-me")
    assert found is not None and found.id == row.id
