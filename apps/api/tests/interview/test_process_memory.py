"""Process memory document tests for src/realmock/domains/interview/protocols/process_memory.py.

Covers: corrupt-payload degradation with raw backup, write-back preservation
Conventions: deterministic asserts only, no IO
"""

from __future__ import annotations

import json

from realmock.domains.interview.protocols.process_memory import (
    CORRUPT_BACKUP_KEY,
    append_round,
    dump_memory,
    empty_memory,
    load_memory,
    render_for_prompt,
)


def test_load_memory_valid_document_has_no_backup_key():
    doc = load_memory(dump_memory(empty_memory()))
    assert CORRUPT_BACKUP_KEY not in doc
    assert doc["rounds"] == []


def test_load_memory_corrupt_json_keeps_raw_backup():
    raw = '{"schema": "realmock.process_memory.v1", "rounds": [truncat'
    doc = load_memory(raw)
    assert doc["rounds"] == []
    assert doc[CORRUPT_BACKUP_KEY] == raw


def test_load_memory_non_object_keeps_raw_backup():
    raw = json.dumps([1, 2, 3])
    doc = load_memory(raw)
    assert doc[CORRUPT_BACKUP_KEY] == raw


def test_write_back_preserves_corrupt_backup():
    raw = "{broken json payload"
    doc = load_memory(raw)
    append_round(
        doc,
        round_no=2,
        session_id=7,
        result="passed",
        digest={"summary": "round two digest"},
    )
    reloaded = json.loads(dump_memory(doc))
    # The corruption degrades this round's read but the prior raw history
    # survives the write-back instead of being silently destroyed.
    assert reloaded[CORRUPT_BACKUP_KEY] == raw
    assert [r["round_no"] for r in reloaded["rounds"]] == [2]


def test_render_ignores_backup_key():
    doc = load_memory("{broken")
    assert render_for_prompt(doc) == ""
