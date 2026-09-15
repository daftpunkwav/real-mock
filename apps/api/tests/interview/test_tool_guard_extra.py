"""Tool guard tests for src/realmock/domains/interview/agents/tool_guard.py.

Covers: _scope non-dict, _box failure/non-mapping branches (existing test_tool_guard.py kept)
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


# ---- prompt_assembler (57, 81-82, 109-110, 117, 133, 144) ----










# ---- history_compaction (118-119, 138-139, 152-153) ----


def _fold_agent(n=12):
    messages: list[dict[str, Any]] = [{"role": "system", "content": "rules"}]
    for i in range(n):
        messages.append({"role": "assistant", "content": f"Q{i} " + "x" * 200})
        messages.append({"role": "user", "content": f"A{i} " + "y" * 200})
    return SimpleNamespace(messages=messages, agent_state={})








# ---- past_records (29-31, 68-69) ----




# ---- session_prompt (237, 315-316, 397-398) ----


def _sp_mixin(**overrides):
    from realmock.domains.interview.agents.session_prompt import SessionPromptMixin

    m = SessionPromptMixin()
    m.session = SimpleNamespace(
        role="Backend",
        level="Senior",
        company="bytedance",
        workflow_type="technical",
        personality="professional",
        strictness=3,
        interview_style="deep_dive",
        resume_id=1,
        profile_id=1,
        round_no=1,
        process_id=None,
    )
    m.agent_state = {}
    m.messages = [{"role": "system", "content": "base"}]
    m.workflow = SimpleNamespace(id="technical", name="Technical", phases=[])
    m.plan = None
    for k, v in overrides.items():
        setattr(m, k, v)
    return m








# ---- tool_guard (74, 109-110, 116, 127) ----


def test_tool_guard_scope_non_dict() -> None:
    from realmock.domains.interview.agents.tool_guard import _scope

    assert _scope(None) == ("", "")
    assert _scope("bad") == ("", "")


def test_tool_guard_box_branches() -> None:
    from realmock.domains.interview.agents.tool_guard import GUARD_STATE_KEY, ToolGuard

    def _boom_state():
        raise RuntimeError("state down")

    g = ToolGuard(state_fn=_boom_state)
    box = g._box()
    assert isinstance(box, dict)

    g2 = ToolGuard(state_fn=lambda: {GUARD_STATE_KEY: "not-a-mapping"})
    assert g2._box(create=True) is g2._scratch

    g3 = ToolGuard()
    g3._local_box = {GUARD_STATE_KEY: "bad"}  # type: ignore[assignment]
    assert g3._box(create=False) is g3._scratch
