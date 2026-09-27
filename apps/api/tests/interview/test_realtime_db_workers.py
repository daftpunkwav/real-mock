# -*- coding: utf-8 -*-
"""Real-SQLite regression for the realtime DB worker helpers (batch D1).

The handler-level tests mock these workers away, so nothing used to verify
the actual persistence. These cases drive the sync workers against the
conftest file-backed sessions DB:

- ``_read_persona_sync`` loads the persona scalars (None when the row is gone);
- ``_append_silence_flag_sync`` lands the probe flag on the newest ledger turn
  of a freshly loaded row;
- ``_finish_notify_sync`` freezes the session and snapshots the outcome;
  the second call reports ``already_frozen`` (idempotent notify);
- ``_persist_interrupt_stats_sync`` writes the merged interrupt state.
"""

from __future__ import annotations

import json


from realmock.domains.interview.models import InterviewSession, InterviewTurn
from realmock.domains.interview.realtime.control.interrupt import (
    InterruptControlMixin,
)
from realmock.domains.interview.realtime.control.silence_nudge import (
    _append_silence_flag_sync,
    _read_persona_sync,
)
from realmock.domains.interview.realtime.report_scheduler import (
    _finish_notify_sync,
)
from realmock.platform.core.constants import SessionStatus


def _mk_session(db, **overrides) -> InterviewSession:
    base = dict(
        profile_id=1,
        role="Backend",
        level="intermediate",
        company="acme",
        workflow_type="technical",
        personality="professional",
        strictness=3,
        interview_style="deep_dive",
        status=SessionStatus.ACTIVE.value,
        current_phase="basic_knowledge",
        messages="[]",
        agent_state="{}",
    )
    base.update(overrides)
    row = InterviewSession(**base)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _seed_turn(db, session_id: int, turn: dict, seq: int = 1) -> None:
    db.add(
        InterviewTurn(
            session_id=session_id,
            turn_id=str(turn.get("turn_id") or f"t-{seq:04d}"),
            seq=seq,
            turn=json.dumps(turn, ensure_ascii=False),
        )
    )
    db.commit()


def test_read_persona_sync_loads_scalars(db) -> None:
    row = _mk_session(db)
    persona = _read_persona_sync(row.id)
    assert persona == ("professional", 3, "basic_knowledge")
    assert _read_persona_sync(row.id + 999) is None


def test_append_silence_flag_sync_writes_newest_turn(db) -> None:
    row = _mk_session(db)
    _seed_turn(db, row.id, {"turn_id": "t-0001", "flags": {}})
    _append_silence_flag_sync(row.id, {"seq": 1, "text": "still there?"})
    rows = (
        db.query(InterviewTurn)
        .filter(InterviewTurn.session_id == row.id)
        .order_by(InterviewTurn.seq)
        .all()
    )
    doc = json.loads(rows[-1].turn)
    assert doc["flags"]["silence_probe"] == {"seq": 1, "text": "still there?"}


def test_finish_notify_sync_freezes_and_is_idempotent(db) -> None:
    row = _mk_session(db)
    # First call: runs the finish lifecycle (complete + freeze). found=True;
    # score/result are legitimately None (the debrief writes the score later).
    found, already_frozen, score, result = _finish_notify_sync(row.id)
    assert found is True
    assert already_frozen is False
    assert score is None and result is None
    db.expire_all()
    fresh = db.query(InterviewSession).filter(InterviewSession.id == row.id).first()
    assert fresh.status == SessionStatus.COMPLETED.value
    assert fresh.ledger_frozen is True
    # Second call: reports already_frozen so the caller only notifies.
    found2, already_frozen2, _, _ = _finish_notify_sync(row.id)
    assert found2 is True
    assert already_frozen2 is True


def test_finish_notify_sync_missing_row_is_found_false(db) -> None:
    """A missing row must be distinguishable from a first finish (both have
    None score/result) — the caller gates the interview_complete frame on it."""
    found, already_frozen, score, result = _finish_notify_sync(999999)
    assert found is False
    assert already_frozen is False
    assert score is None and result is None


def test_persist_interrupt_stats_sync_writes_state(db) -> None:
    row = _mk_session(db)
    worker = InterruptControlMixin._persist_interrupt_stats_sync
    state = {"candidate_interrupts": 2, "ai_interrupts": 1}
    assert (
        worker(None, row.id, json.dumps(state, ensure_ascii=False))  # type: ignore[arg-type]
        is True
    )
    db.expire_all()
    fresh = db.query(InterviewSession).filter(InterviewSession.id == row.id).first()
    assert json.loads(fresh.agent_state)["candidate_interrupts"] == 2
    # A missing row reports failure instead of raising.
    assert worker(None, row.id + 999, "{}") is False  # type: ignore[arg-type]
