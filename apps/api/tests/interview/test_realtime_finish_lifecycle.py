"""Finish lifecycle tests for agents/finish_lifecycle.py.

Covers: mark-completed with freeze, frozen load path, non-list messages path.
Conventions: no real network/LLM (all external calls mocked); uses SimpleNamespaceLike session stub.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

class SimpleNamespaceLike:
    """Minimal attribute bag standing in for an ORM session row."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

@pytest.mark.asyncio
async def test_run_finish_lifecycle_branches():
    from realmock.domains.interview.agents import finish_lifecycle as mod

    # mark_completed with pending -> commit; not frozen -> freeze; corrupt messages
    sess = SimpleNamespaceLike(status="active", ended_at=None, id=7, messages="not-json", profile_id=1, resume_id=None, role="BE", level="S", company="Acme", workflow_type="technical", personality="professional", strictness=3, interview_style="deep_dive", started_at=None, overall_score=None, process_id=None, round_no=None, result=None)
    db = MagicMock()
    with (
        patch.object(mod, "is_frozen", return_value=False),
        patch.object(mod, "freeze_ledger", return_value={"turns": []}) as fr,
        patch("realmock.domains.interview.process.process_service.record_round_finished", return_value=None),
        patch.object(mod, "notify_interview_finished", return_value=None),
    ):
        out = mod.run_finish_lifecycle(db, sess, mark_completed=True)
        assert out == {"turns": []}
        assert sess.status == "completed"
        assert sess.ended_at is not None
        fr.assert_called_once()
        db.commit.assert_called()
    # already frozen -> load_ledger, messages list counted
    sess2 = SimpleNamespaceLike(status="completed", ended_at="x", id=8, messages=json.dumps([{"a": 1}, {"b": 2}]), profile_id=0, resume_id=None, role="", level="", company="", workflow_type="", personality="", strictness=0, interview_style="", started_at=None, overall_score=5, process_id=None, round_no=None, result=None)
    db2 = MagicMock()
    with (
        patch.object(mod, "is_frozen", return_value=True),
        patch.object(mod, "load_ledger", return_value={"frozen": True}),
        patch("realmock.domains.interview.process.process_service.record_round_finished", return_value=None),
        patch.object(mod, "notify_interview_finished", return_value=None),
    ):
        out2 = mod.run_finish_lifecycle(db2, sess2, mark_completed=True)
        assert out2 == {"frozen": True}
        db2.commit.assert_not_called()
    # messages non-list + mark_completed False
    sess3 = SimpleNamespaceLike(status="active", ended_at="y", id=9, messages=json.dumps({"not": "list"}), profile_id=0, resume_id=None, role="r", level="l", company="c", workflow_type="w", personality="p", strictness=1, interview_style="s", started_at=None, overall_score=None, process_id=None, round_no=None, result=None)
    with (
        patch.object(mod, "is_frozen", return_value=True),
        patch.object(mod, "load_ledger", return_value={}),
        patch("realmock.domains.interview.process.process_service.record_round_finished", return_value=None),
        patch.object(mod, "notify_interview_finished", return_value=None),
    ):
        mod.run_finish_lifecycle(MagicMock(), sess3, mark_completed=False)
        assert sess3.status == "active"

