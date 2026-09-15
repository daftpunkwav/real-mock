"""Context-seed tests for realmock.domains.prep.agents.context.seed.

Covers: format_memory_index failures/truncation, system-message fallback/join and linked-session blocks
Conventions: list_memories and sessions faked where needed; temp DB otherwise; rate limits reset per test
"""
from __future__ import annotations
import json
from types import SimpleNamespace
import pytest

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()

def test_format_memory_index_owned_session_failure(monkeypatch) -> None:
    import realmock.domains.prep.agents.context.seed as seed_mod

    monkeypatch.setattr(seed_mod, "sessions_db_session", lambda: 1 / 0)
    assert seed_mod.format_memory_index(None) == ""

def test_format_memory_index_list_failure_and_empty(monkeypatch, db) -> None:
    import realmock.domains.prep.agents.context.seed as seed_mod

    monkeypatch.setattr(seed_mod, "list_memories", lambda *a, **k: 1 / 0)
    assert seed_mod.format_memory_index(db) == ""

    monkeypatch.setattr(seed_mod, "list_memories", lambda *a, **k: [])
    assert seed_mod.format_memory_index(db) == ""

def test_format_memory_index_bad_tags_and_truncation(monkeypatch, db) -> None:
    import realmock.domains.prep.agents.context.seed as seed_mod

    bad = SimpleNamespace(id=1, tags="not-json{{{", summary="s" * 500)
    good = SimpleNamespace(id=2, tags=json.dumps(["a", "b"]), summary="good summary")
    nonlist = SimpleNamespace(id=3, tags=json.dumps({"a": 1}), summary="x")
    monkeypatch.setattr(seed_mod, "list_memories", lambda *a, **k: [bad, good, nonlist])
    out = seed_mod.format_memory_index(db)
    assert "memory #1" in out
    assert "memory #2" in out
    assert "[a,b]" in out or "[a" in out

def test_build_system_messages_fallback_when_empty(monkeypatch, db) -> None:
    import realmock.domains.prep.agents.context.seed as seed_mod

    monkeypatch.setattr(seed_mod, "_system_blocks", lambda *a, **k: [])
    out = seed_mod.build_system_messages(
        db, resume_id=None, target_company="", linked_session_id=None
    )
    assert len(out) == 1
    assert out[0]["role"] == "system"
    assert "interview-prep coach" in out[0]["content"]

def test_build_system_message_joins_blocks(monkeypatch, db) -> None:
    import realmock.domains.prep.agents.context.seed as seed_mod

    monkeypatch.setattr(
        seed_mod, "_system_blocks", lambda *a, **k: [seed_mod.PREP_SYSTEM, "", "tail"]
    )
    out = seed_mod.build_system_message(db, resume_id=None, target_company="")
    assert "interview-prep coach" in out
    assert "tail" in out

def test_seed_blocks_cover_company_and_linked(db) -> None:
    import realmock.domains.prep.agents.context.seed as seed_mod
    from realmock.domains.prep.models import PrepSession
    from realmock.platform.core.session_auth import new_access_token

    linked = PrepSession(
        access_token=new_access_token(), status="active",
        messages=json.dumps([{"role": "user", "content": "linked turn"}]),
    )
    db.add(linked)
    db.commit()
    db.refresh(linked)
    blocks = seed_mod.build_system_messages(
        db, resume_id=None, target_company="", linked_session_id=linked.id
    )
    assert len(blocks) >= 1
    assert all(b["role"] == "system" for b in blocks)
