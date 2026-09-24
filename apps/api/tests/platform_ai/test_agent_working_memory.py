"""Working memory tests for apps/api/src/realmock/platform/capabilities/ai/agent/working_memory.py.

Covers: bounded remember/append, from_state/to_state_patch, absorb_omitted,
dump_block/load_from_messages and render branches.

Conventions: pure functions, no network; asyncio_mode=auto.
"""

from __future__ import annotations

from realmock.platform.capabilities.ai.agent.working_memory import WorkingMemory



def test_bounded_append_edges() -> None:
    m = WorkingMemory()
    m.remember("asked", "")  # empty → no-op
    m.remember("asked", "q1")
    m.remember("asked", "q1")  # dup → no-op
    assert m.asked == ["q1"]
    for i in range(20):
        m.remember("note", f"n{i}")
    assert len(m.notes) == 16
    assert "n0" not in m.notes[0]


def test_from_state_findings_and_clips() -> None:
    m = WorkingMemory.from_state({
        "asked_questions": ["q1", None, "q2"],
        "weak_points": ["w"],
        "github_findings": [{"tool": "web", "preview": "abc"}, "plain"],
        "company_findings": [{"tool": "", "preview": ""}],
        "memory_notes": ["n"],
        "pending_quiz": "z" * 300,
    })
    assert m.asked == ["q1", "q2"]
    assert m.findings[0] == "web: abc"
    assert "plain" in m.findings
    assert len(m.pending_quiz) <= 240


def test_state_patch_and_remember_kinds() -> None:
    m = WorkingMemory()
    assert "pending_quiz" not in m.to_state_patch()
    m.remember("weak", "w1")
    m.remember("finding", "f1")
    m.remember("quiz", "q" * 300)
    m.remember("other", "note1")
    patch = m.to_state_patch()
    assert patch["weak_points"] == ["w1"]
    assert patch["pending_quiz"] == "q" * 239 + "…"
    assert m.pending_quiz in m.render()
    assert "Weak spots: w1" in m.render()
    assert "Verified: f1" in m.render()
    assert "Covered:" not in m.render()


def test_absorb_omitted_list_content_and_limit() -> None:
    m = WorkingMemory()
    m.absorb_omitted([
        {"role": "system", "content": "skip"},
        {"role": "tool", "content": "skip"},
        {"role": "user", "content": [{"text": "hello"}, {"image_url": {}}]},
        {"role": "assistant", "content": ""},
    ])
    assert "user:hello" in m.notes[0]
    m2 = WorkingMemory()
    m2.absorb_omitted([])  # nothing → no note
    assert m2.notes == []
    m3 = WorkingMemory()
    m3.absorb_omitted([{"role": "user", "content": f"m{i}"} for i in range(20)], limit=3)
    assert "m3" not in m3.notes[0]


def test_dump_and_load_block() -> None:
    assert WorkingMemory().dump_block().startswith("[Working memory]\n")
    m = WorkingMemory(notes=["n1"])
    loaded = WorkingMemory.load_from_messages([{"role": "system", "content": m.dump_block()}])
    assert loaded.notes == ["n1"]
    legacy = WorkingMemory.load_from_messages([
        {"role": "system", "content": "[working memory]\n{\"memory_notes\": [\"old\"]}\nNotes: old"},
        {"role": "system", "content": ["not", "str"]},
        {"role": "user", "content": "x"},
    ])
    assert legacy.notes == ["old"]
    broken = WorkingMemory.load_from_messages([
        {"role": "system", "content": "[Working memory]\nnot-json{"},
    ])
    assert broken.notes == []
    assert WorkingMemory.load_from_messages([]).notes == []


def test_absorb_omitted_digest_survives_the_note_clip() -> None:
    """The digest note gets its own budget: several exchanges must survive,
    not just the first one and a half (regular notes clip at 160 chars)."""
    m = WorkingMemory()
    m.absorb_omitted([
        {"role": "user", "content": f"question number {i} about topic {i}"} for i in range(6)
    ])
    note = m.notes[0]
    assert len(note) <= 560
    assert "question number 5" in note, "later collected exchanges must survive the clip"
    assert "question number 0" in note
    # The digest stays a normal bounded note afterwards (16-slot eviction).
    assert len(m.notes) == 1
