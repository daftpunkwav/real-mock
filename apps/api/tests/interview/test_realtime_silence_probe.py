"""Silence probe tests for realtime/control/silence_probe.py.

Covers: flow language, probe system prompt variants, clamp wait helper,
generate probe LLM branches (empty/success/json/think/exception).
Conventions: no real network/LLM (all external calls mocked); uses _make_handler for handler construction.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from realmock.domains.interview.realtime.control.silence_nudge import clamp_nudge_wait
from realmock.domains.interview.realtime.control.silence_probe import flow_language, probe_system_prompt
from realmock.domains.interview.realtime.core.session_registry import reset_session_registry_for_tests
from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler

def _make_handler(sid=1):
    """Build a mocked InterviewWSHandler bound to an in-memory websocket."""
    ws = MagicMock(accept=AsyncMock(), send_json=AsyncMock(), receive_json=AsyncMock(), close=AsyncMock())
    return InterviewWSHandler(ws, session_id=sid)


async def _agen(items):
    """Yield canned stream events for deterministic streaming tests."""
    for i in items:
        yield i

@pytest.mark.asyncio
async def test_flow_language_and_prompt_and_clamp():
    reset_session_registry_for_tests()
    try:
        assert flow_language(None) == "zh"
        assert flow_language(SimpleNamespace(plan=SimpleNamespace(source="agent", language="en-US"))) == "en"
        assert flow_language(SimpleNamespace(plan=SimpleNamespace(source="other", language="en"))) == "zh"
        assert "first probe" in probe_system_prompt(attempt=1, lang="en")
        assert "second probe" in probe_system_prompt(attempt=2, lang="en")
        assert "first probe" in probe_system_prompt(attempt=1, lang="zh")
        assert "second probe" in probe_system_prompt(attempt=3, lang="zh")
        assert clamp_nudge_wait(0, 0) == 7.0
        assert clamp_nudge_wait(-5, 10) == 10.0
        assert clamp_nudge_wait(100, 10) == 60.0
        assert clamp_nudge_wait(20, 10) == 20.0
        assert clamp_nudge_wait(0, 10) == 10.0
        h = _make_handler()
        try:
            h.ctx.agent = SimpleNamespace(plan=SimpleNamespace(source="agent", language="en"))
            assert h._nudge_language() == "en"
        finally:
            await h._cancel_bg_tasks()
    finally:
        reset_session_registry_for_tests()


@pytest.mark.asyncio
async def test_generate_silence_probe_branches():
    h = _make_handler()
    try:
        # llm None -> ""
        h.ctx.llm = None
        h.ctx.agent = MagicMock()
        h.ctx.agent.plan = SimpleNamespace(source="agent", language="zh")
        assert await h._generate_silence_probe(question="q?", probe_hint="", attempt=1, silent_sec=0) == ""
        # success raw non-json
        h.ctx.llm = MagicMock()
        h.ctx.llm.chat = AsyncMock(return_value="自然追问一下?")
        out = await h._generate_silence_probe(question="讲讲项目?", probe_hint="hint", attempt=1, silent_sec=5)
        assert out == "自然追问一下?"
        # json dict with say
        h.ctx.llm.chat = AsyncMock(return_value='{"say": "换个角度讲讲?"}')
        out2 = await h._generate_silence_probe(question="q", probe_hint="", attempt=2, silent_sec=0)
        assert out2 == "换个角度讲讲?"
        # json dict without say -> raw slice
        h.ctx.llm.chat = AsyncMock(return_value='{"nosay": 1}')
        out3 = await h._generate_silence_probe(question="q", probe_hint="", attempt=1, silent_sec=0)
        assert out3 == '{"nosay": 1}'[:120]
        # json list -> raw slice
        h.ctx.llm.chat = AsyncMock(return_value='[1,2]')
        out4 = await h._generate_silence_probe(question="q", probe_hint="", attempt=1, silent_sec=0)
        assert out4 == "[1,2]"
        # exception -> ""
        h.ctx.llm.chat = AsyncMock(side_effect=RuntimeError("llm boom"))
        assert await h._generate_silence_probe(question="q", probe_hint="", attempt=1, silent_sec=0) == ""
        # think blocks stripped
        h.ctx.llm.chat = AsyncMock(return_value="<think>reason</think>你好吗?")
        out5 = await h._generate_silence_probe(question="q", probe_hint="", attempt=1, silent_sec=0)
        assert "你好吗" in out5
    finally:
        await h._cancel_bg_tasks()

