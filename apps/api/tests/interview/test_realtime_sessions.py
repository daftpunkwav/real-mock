"""Session routes tests for routes/sessions.py.

Covers: resume picker passthrough, create with/without overrides,
list/get/messages branches, response defaults.
Conventions: no real network/LLM (all external calls mocked); uses _session_row helper.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

def _session_row(**kw):
    """Build a minimal session row namespace with sensible defaults."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    base = {
        "id": 1, "role": "BE", "level": "S", "company": "Acme", "workflow_type": "technical",
        "personality": "professional", "strictness": 3, "interview_style": "deep_dive",
        "avatar_id": None, "scene_id": None, "status": "active", "current_phase": "tech",
        "overall_score": None, "process_id": None, "round_no": None, "result": None,
        "plan_status": None, "plan": None, "started_at": now, "ended_at": None,
        "created_at": now, "access_token": "tok",
    }
    base.update(kw)
    return SimpleNamespace(**base)

def test_sessions_crud_gaps():
    from realmock.domains.interview.routes import sessions as mod
    from realmock.domains.interview.schemas import InterviewConfig

    # list_resume_picker passthrough
    with patch.object(mod, "list_resume_picker_items", return_value=[{"id": 1}]) as m:
        assert mod.list_resume_picker(MagicMock()) == [{"id": 1}]
        m.assert_called_once()
    # create without overrides
    cfg = InterviewConfig(role="BE", level="S", company="Acme")
    db = MagicMock()
    # capture added session
    added = {}

    def _add(s):
        added["s"] = s

    db.add = _add
    db.commit = MagicMock()
    db.refresh = MagicMock()
    bg = MagicMock()
    req = MagicMock()
    resp = MagicMock()
    with (
        patch.object(mod, "new_access_token", return_value="tok123"),
        patch.object(mod, "generate_plan_for_session", return_value=None),
        patch.object(mod, "set_session_cookie", return_value=None) as cookie,
        patch.object(mod, "to_session_response", return_value={"id": 9}) as to_resp,
    ):
        out = mod.create_session(cfg, req, resp, bg, db)
        assert out == {"id": 9}
        assert added["s"].access_token == "tok123"
        assert added["s"].ai_overrides == "{}"
        bg.add_task.assert_called_once()
        cookie.assert_called_once()
        to_resp.assert_called_once()
    # create with overrides + locale trim (bypass 10-char validation to hit [:10] slice)
    cfg2 = InterviewConfig.model_construct(role="BE", level="S", company="Acme", workflow_type="technical", personality="professional", strictness=3, interview_style="deep_dive", resume_id=None, avatar_id="a", scene_id="s", ai_overrides=None, ui_locale="zh-CN-extra-long", reference_detail="full")
    cfg2.ai_overrides = SimpleNamespace(model_dump=lambda exclude_none=True: {"k": "v"})
    db2 = MagicMock()
    db2.add = MagicMock()
    db2.commit = MagicMock()
    db2.refresh = MagicMock()
    with (
        patch.object(mod, "new_access_token", return_value="t"),
        patch.object(mod, "generate_plan_for_session", return_value=None),
        patch.object(mod, "set_session_cookie", return_value=None),
        patch.object(mod, "to_session_response", return_value={"id": 1}),
    ):
        mod.create_session(cfg2, MagicMock(), MagicMock(), MagicMock(), db2)
        saved = db2.add.call_args[0][0]
        assert json.loads(saved.ai_overrides) == {"k": "v"}
        assert len(saved.ui_locale) <= 10
    # list_sessions
    db3 = MagicMock()
    db3.query.return_value.order_by.return_value.all.return_value = [_session_row(), _session_row(id=2)]
    with patch.object(mod, "to_session_response", side_effect=lambda s, include_token=False: {"id": s.id}):
        assert mod.list_sessions(db3) == [{"id": 1}, {"id": 2}]
    # get_session 404 / 403 / ok
    db4 = MagicMock()
    db4.query.return_value.filter.return_value.first.return_value = None
    with patch.object(mod, "raise_error", side_effect=RuntimeError("A2001")):
        try:
            mod.get_session(1, db4, "tok")
            assert False
        except RuntimeError:
            pass
    db5 = MagicMock()
    db5.query.return_value.filter.return_value.first.return_value = _session_row()
    with (
        patch.object(mod, "assert_session_token", side_effect=RuntimeError("403")) as at,
        patch.object(mod, "raise_error", return_value=None),
    ):
        try:
            mod.get_session(1, db5, "bad")
            assert False
        except RuntimeError:
            at.assert_called_once()
    with (
        patch.object(mod, "assert_session_token", return_value=None),
        patch.object(mod, "to_session_response", return_value={"id": 1}),
    ):
        assert mod.get_session(1, db5, "tok") == {"id": 1}
    # get_messages 404 / ok / dirty
    db6 = MagicMock()
    db6.query.return_value.filter.return_value.first.return_value = None
    with patch.object(mod, "raise_error", side_effect=RuntimeError("A2001")):
        try:
            mod.get_messages(1, db6, "t")
            assert False
        except RuntimeError:
            pass
    good = _session_row(messages=json.dumps([{"role": "user", "content": "hi"}]))
    db7 = MagicMock()
    db7.query.return_value.filter.return_value.first.return_value = good
    with patch.object(mod, "assert_session_token", return_value=None):
        msgs = mod.get_messages(1, db7, "tok")
        assert msgs[0]["role"] == "user"
    dirty = _session_row(messages=json.dumps([{"bad": 1}]))
    db8 = MagicMock()
    db8.query.return_value.filter.return_value.first.return_value = dirty
    with patch.object(mod, "assert_session_token", return_value=None):
        assert mod.get_messages(1, db8, "tok") == []
    # to_session_response defaults avatar/scene
    with patch.object(mod, "parse_plan", return_value=None), patch.object(mod, "plan_step_views", return_value=[]):
        resp_out = mod.to_session_response(_session_row(), include_token=False)
        assert resp_out.avatar_id == "professional_male"
        assert resp_out.scene_id == "meeting_room"
        assert resp_out.access_token is None
        resp2 = mod.to_session_response(_session_row(avatar_id="a", scene_id="s"), include_token=True)
        assert resp2.avatar_id == "a"
        assert resp2.access_token == "tok"

