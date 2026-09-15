"""Prompt assembler tests for src/realmock/domains/interview/agents/prompt_assembler.py.

Covers: face hint, image/plain branches, compact/token-failure, tech domains/context window
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from contextlib import contextmanager
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


def test_prompt_no_face_hint() -> None:
    from realmock.domains.interview.agents.prompt_assembler import PromptAssembler

    out = PromptAssembler.build_user_content("hello", {"face_detected": False})
    assert "no face detected" in out


@pytest.mark.asyncio
async def test_prompt_image_branch_and_plain_return() -> None:
    from realmock.domains.interview.agents.prompt_assembler import PromptAssembler

    agent = SimpleNamespace(
        messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        agent_state={},
    )
    session = SimpleNamespace(id=1)
    asm = PromptAssembler(session, agent, llm=None)
    out = await asm.build_api_messages("hi", None, "aGVsbG8=", context_window=None)
    assert out[-1]["role"] == "user"
    assert out[-1]["content"][1]["type"] == "image_url"
    # Plain path without context window returns messages as-is (117).
    out2 = await asm.build_api_messages("hi", None, None, context_window=None)
    assert out2 == agent.messages


@pytest.mark.asyncio
async def test_prompt_compact_token_estimate_failure(monkeypatch) -> None:
    from realmock.domains.interview.agents import prompt_assembler as mod

    agent = SimpleNamespace(
        messages=[{"role": "user", "content": "hi"}],
        agent_state={},
    )
    session = SimpleNamespace(id=2)
    asm = mod.PromptAssembler(session, agent, llm=None)

    async def _fake_compact(messages, context_window, **k):
        return [{"role": "user", "content": "short"}]

    def _boom(messages):
        raise RuntimeError("tok down")

    monkeypatch.setattr(mod, "compact_with_summary", _fake_compact)
    monkeypatch.setattr(mod, "estimate_messages_tokens", _boom)
    monkeypatch.setattr(mod, "adaptive_fold_thresholds", lambda w: (0.3, 0.5))
    out = await asm.build_api_messages("hi", None, None, context_window=2000)
    assert out == [{"role": "user", "content": "short"}]


def test_prompt_tech_domains_and_context_window(monkeypatch) -> None:
    from realmock.domains.interview.agents import prompt_assembler as mod

    agent = SimpleNamespace(
        messages=[],
        agent_state={},
        get_user_profile=lambda db: SimpleNamespace(tech_domains_list=[]),
    )
    asm = mod.PromptAssembler(SimpleNamespace(id=1), agent, llm=None)
    assert asm.get_tech_domains(None) == []  # type: ignore[arg-type]
    agent2 = SimpleNamespace(
        messages=[],
        agent_state={},
        get_user_profile=lambda db: SimpleNamespace(tech_domains_list=["Python"]),
    )
    asm2 = mod.PromptAssembler(SimpleNamespace(id=1), agent2, llm=None)
    assert asm2.get_tech_domains(None) == ["Python"]  # type: ignore[arg-type]

    @contextmanager
    def _fake_api():
        yield SimpleNamespace()

    monkeypatch.setattr(mod, "api_db_session", _fake_api)
    monkeypatch.setattr(mod, "get_stage_config_for_runtime", lambda db, stage: {})
    assert asm.get_context_window(None) == 0  # type: ignore[arg-type]


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




