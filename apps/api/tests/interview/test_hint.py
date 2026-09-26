"""Reference-answer service: extraction, terminal-event guarantees, full-mode fallback."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from realmock.domains.interview.agents.hint.hint_answer import generate_full_reference_hint
from realmock.domains.interview.realtime.control.hint import ReferenceHintMixin
from realmock.domains.interview.schemas import InterviewConfig


def _mixin(**ctx_kwargs) -> ReferenceHintMixin:
    mixin = ReferenceHintMixin()
    ctx = SimpleNamespace(
        session_id=1,
        llm=None,
        agent=None,
        hint_inflight=None,
        reference_detail="outline",
    )
    for key, value in ctx_kwargs.items():
        setattr(ctx, key, value)
    mixin.ctx = ctx  # type: ignore[attr-defined]
    mixin.sent: list[tuple[str, dict]] = []  # type: ignore[attr-defined]

    async def send(event: str, **payload) -> None:
        mixin.sent.append((event, payload))  # type: ignore[attr-defined]

    mixin.send = send  # type: ignore[method-assign]
    return mixin


def test_extract_hint_question_picks_last_question():
    extract = ReferenceHintMixin._extract_hint_question
    assert extract("Long intro line\n请介绍一下你自己？") == "请介绍一下你自己？"
    assert extract("") == ""
    assert extract("no question here\nstill none") == "still none"


_PROMPT_SHAPE = (
    "You are the AI interviewer...\n{persona}\n\n"
    "## Interview setup\nRole: Backend\n\n"
    "## Candidate profile\nName: Ada\nSkills: Redis, Kafka\n\n"
    "## Current phase\nPhase: project_deep_dive\n\n"
    "## Behavior rules\n1. x\n"
)


def test_candidate_slice_cuts_grounding_not_persona():
    content = _PROMPT_SHAPE.format(persona="## How you talk\n- be brief")
    sl = ReferenceHintMixin._candidate_slice(content, limit=1200)
    assert "Candidate profile" in sl
    assert "Ada" in sl
    assert "How you talk" not in sl
    assert "Behavior rules" not in sl


def test_candidate_slice_falls_back_to_head_without_markers():
    sl = ReferenceHintMixin._candidate_slice("no recognizable sections", limit=10)
    assert sl == "no recogni"


def test_hint_language_defaults_to_zh():
    assert _mixin()._hint_language() == "zh"


def test_hint_language_follows_agent_plan():
    plan = SimpleNamespace(source="agent", language="en")
    agent = SimpleNamespace(plan=plan, messages=[])
    assert _mixin(agent=agent)._hint_language() == "en"
    plan.language = "zh-CN"
    assert _mixin(agent=agent)._hint_language() == "zh"


def test_empty_question_ends_with_terminal_hint():
    mixin = _mixin()
    asyncio.run(mixin._on_request_hint({"question": "   "}))
    assert len(mixin.sent) == 1
    event, payload = mixin.sent[0]
    assert event == "reference_hint"
    assert payload["content"].strip()


def test_duplicate_inflight_resends_loading_not_silence():
    """Same-question regen while generating must re-announce loading (bug: silent swallow)."""
    mixin = _mixin(llm=SimpleNamespace())
    mixin.ctx.hint_inflight = "请介绍一下你自己？"
    asyncio.run(mixin._on_request_hint({"question": "请介绍一下你自己？"}))
    assert len(mixin.sent) == 1
    event, payload = mixin.sent[0]
    assert event == "reference_hint_loading"
    assert payload["question"] == "请介绍一下你自己？"


def test_rate_limited_ends_with_terminal_error():
    """Rate-limiting must resolve loading via reference_hint_error (bug: stuck 25s)."""
    mixin = _mixin()
    asyncio.run(mixin._hint_rate_limited({"question": "讲讲你的项目？"}))
    assert len(mixin.sent) == 1
    event, payload = mixin.sent[0]
    assert event == "reference_hint_error"
    assert payload["question"] == "讲讲你的项目？"
    assert payload["message"].strip()


def test_full_mode_failure_yields_none_for_outline_degrade():
    """Full loop with a dead LLM returns None so the caller degrades to outline."""

    class DeadLLM:
        async def chat(self, *args, **kwargs):
            raise RuntimeError("no backend")

    result = asyncio.run(
        generate_full_reference_hint(
            llm=DeadLLM(),
            db=SimpleNamespace(),
            session=SimpleNamespace(id=9, resume_id=None, profile_id=None),
            agent_state={},
            question="讲讲你的项目？",
            background="",
            budget_seconds=5.0,
        )
    )
    assert result is None


def test_reference_detail_defaults_to_outline():
    config = InterviewConfig(role="Backend", level="Senior", company="Acme")
    assert config.reference_detail == "outline"


def test_full_hint_reuses_loop_answer_without_writer_call(monkeypatch):
    """When the tool loop already produced the answer, skip the second LLM call."""
    import realmock.domains.interview.agents.hint.hint_answer as mod
    from types import SimpleNamespace as NS

    calls = {"chat": 0}

    class CountingLLM:
        async def chat(self, *args, **kwargs):
            calls["chat"] += 1
            return "fallback answer"

    async def fake_loop(llm, messages, **kwargs):
        return NS(
            final_content="I designed the rate limiter using a token bucket...",
            tool_used=True,
            messages=[],
            thinking="",
        )

    monkeypatch.setattr(mod, "run_agent_loop", fake_loop)
    result = asyncio.run(
        mod._generate(
            CountingLLM(), NS(), NS(id=1, resume_id=None, profile_id=None), {},
            "讲讲限流？", "", "zh",
        )
    )
    assert result.startswith("I designed the rate limiter")
    assert calls["chat"] == 0  # writer pass skipped entirely


def test_full_hint_falls_back_to_writer_without_loop_content(monkeypatch):
    import realmock.domains.interview.agents.hint.hint_answer as mod
    from types import SimpleNamespace as NS

    class WriterLLM:
        async def chat(self, *args, **kwargs):
            return "writer answer"

    async def fake_loop(llm, messages, **kwargs):
        return NS(final_content=None, tool_used=True, messages=[{"role": "user", "content": "q"}], thinking="")

    monkeypatch.setattr(mod, "run_agent_loop", fake_loop)
    result = asyncio.run(
        mod._generate(
            WriterLLM(), NS(), NS(id=1, resume_id=None, profile_id=None), {},
            "Q?", "", "zh",
        )
    )
    assert result == "writer answer"


# ---- tool-free final round and writer message shaping ----


def test_full_hint_enables_tool_free_final_round(monkeypatch):
    import realmock.domains.interview.agents.hint.hint_answer as mod
    from types import SimpleNamespace as NS

    captured: dict = {}

    async def fake_loop(llm, messages, **kwargs):
        captured.update(kwargs)
        return NS(final_content="answer text", tool_used=True, messages=[], thinking="")

    monkeypatch.setattr(mod, "run_agent_loop", fake_loop)
    result = asyncio.run(
        mod._generate(
            SimpleNamespace(), NS(), NS(id=1, resume_id=None, profile_id=None), {},
            "Q?", "", "zh",
        )
    )
    assert result == "answer text"
    assert captured["final_round_tool_free"] is True
    assert "tools are no longer available" in captured["wrap_up_hint"]["content"]
    assert captured["error_context"]["domain"] == "interview"


def test_writer_view_folds_tool_evidence_and_strips_tool_fields():
    import json as _json

    from realmock.domains.interview.agents.hint.hint_answer import _writer_view

    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "q"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c1", "function": {"name": "web_fetch", "arguments": "{}"}}],
            "thinking_blocks": [{"t": 1}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "PAGE CONTENT"},
        {"role": "assistant", "content": "narration kept"},
    ]
    view = _writer_view(messages)
    assert all(m.get("role") != "tool" for m in view)
    assert all("tool_calls" not in m and "thinking_blocks" not in m for m in view)
    joined = _json.dumps(view, ensure_ascii=False)
    assert "PAGE CONTENT" in joined
    assert "[web_fetch]" in joined
    assert "narration kept" in joined


def test_full_hint_writer_receives_sanitized_messages(monkeypatch):
    import realmock.domains.interview.agents.hint.hint_answer as mod
    from types import SimpleNamespace as NS

    captured: dict = {}

    class WriterLLM:
        async def chat(self, messages, **kwargs):
            captured["messages"] = messages
            return "writer answer"

    async def fake_loop(llm, messages, **kwargs):
        return NS(
            final_content=None,
            tool_used=True,
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "q"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": "c1", "function": {"name": "web_fetch", "arguments": "{}"}}],
                },
                {"role": "tool", "tool_call_id": "c1", "content": "COMPANY FACTS"},
            ],
            thinking="",
        )

    monkeypatch.setattr(mod, "run_agent_loop", fake_loop)
    result = asyncio.run(
        mod._generate(
            WriterLLM(), NS(), NS(id=1, resume_id=None, profile_id=None), {},
            "Q?", "", "zh",
        )
    )
    assert result == "writer answer"
    sent = captured["messages"]
    assert all("tool_calls" not in m and "thinking_blocks" not in m for m in sent)
    assert any("COMPANY FACTS" in str(m.get("content")) for m in sent)
