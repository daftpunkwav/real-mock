"""Past records tests for src/realmock/domains/interview/agents/past_records.py.

Covers: _load_ledger corrupt, _turn_text str variants
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


def test_past_records_corrupt_and_str_vals() -> None:
    from realmock.domains.interview.agents import past_records as mod

    bad = SimpleNamespace(id=1, ledger="not-json{")
    assert mod._load_ledger(bad) == []  # type: ignore[arg-type]
    assert mod._turn_text({"assistant": "plain string", "user": "u2"}) != ""
    assert mod._turn_text({"assistant": {"text": "hi"}, "user": None}) != ""


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




