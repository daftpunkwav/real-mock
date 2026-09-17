"""Runner turn tests for agents/interviewer/runner_turn.py.

Covers: completed/error outcomes, regen and ledger failure, background timeouts,
early tool yield with pace prefix, finish triggering, fallback and generic errors.
Conventions: no real network/LLM (all external calls mocked); uses _mk_runner variants for runner stubs.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from realmock.domains.interview.agents.events import EventKind, StreamEvent
from realmock.domains.interview.agents.interviewer.runner_turn import stream_turn
from realmock.domains.interview.agents.turn_output import TurnOutput

def _mk_runner():
    """Base runner stub: active session, 12 asked questions, no pace message."""
    r = MagicMock()
    r.session.status = "active"
    r.session.id = 1
    r.session.started_at = None
    r.agent.record_user_text = MagicMock()
    r.agent.cognitive_memory.working_memory.pending_probes = []
    r.agent.messages = [{"role": "assistant", "content": "Q1"}]
    r.agent.current_phase.return_value.id = "p1"
    r.agent.agent_state = {"asked_questions": ["q"] * 12}
    r.agent.pace_message.return_value = None
    r.agent.record_assistant_text = MagicMock()
    r.agent.note_turn_output = MagicMock()
    r.agent.apply_plan_ops = MagicMock()
    r.agent.advance_phase_if_needed.return_value = False
    r.agent.save_state = MagicMock()
    r.agent.phase_title_for_display.return_value = "T"
    r.prompter.last_assistant_question.return_value = "Q1"
    r.prompter.get_tech_domains.return_value = []
    r.prompter.build_user_content = MagicMock()
    r.prompter.get_context_window.return_value = 1000
    r.prompter.build_api_messages = AsyncMock(return_value=[{"role": "user", "content": "hi"}])
    r.tools.maybe_retrieve_rag = AsyncMock(return_value=None)
    r.shadow_evaluator.evaluate_turn = AsyncMock(return_value=None)
    r.process_orchestrator.decide_next_step = AsyncMock(return_value=MagicMock(directive="a", reason="r", target_topic="t"))
    r.llm = MagicMock(api_key="sk")
    r.spawn_bg_task = MagicMock(side_effect=lambda coro: asyncio.create_task(coro))
    return r


def _mk_runner_pace(qn=0):
    """Runner stub with optional pending probe that triggers a pace prefix."""
    r = MagicMock()
    r.session.status = "active"
    r.session.id = 1
    r.session.started_at = None
    r.agent.record_user_text = MagicMock()
    r.agent.cognitive_memory.working_memory.pending_probes = ["probe1"] if qn else []
    r.agent.messages = [{"role": "assistant", "content": "Q"}]
    r.agent.current_phase.return_value.id = "p1"
    r.agent.agent_state = {"asked_questions": []}
    r.agent.pace_message.return_value = "[Pace: hurry]" if qn else None
    r.agent.record_assistant_text = MagicMock()
    r.agent.note_turn_output = MagicMock()
    r.agent.apply_plan_ops = MagicMock()
    r.agent.advance_phase_if_needed.return_value = False
    r.agent.save_state = MagicMock()
    r.agent.phase_title_for_display.return_value = "T"
    r.agent.note_verdict = MagicMock()
    r.agent.mark_completed = MagicMock()
    r.prompter.last_assistant_question.return_value = "Q"
    r.prompter.get_tech_domains.return_value = []
    r.prompter.build_user_content = MagicMock()
    r.prompter.get_context_window.return_value = 1000
    r.prompter.build_api_messages = AsyncMock(return_value=[{"role": "user", "content": "hi"}])
    r.tools.maybe_retrieve_rag = AsyncMock(return_value=None)
    r.shadow_evaluator.evaluate_turn = AsyncMock(return_value=None)
    r.process_orchestrator.decide_next_step = AsyncMock(return_value=MagicMock(directive="a", reason="r", target_topic="t"))
    r.llm = MagicMock(api_key="sk")
    r.spawn_bg_task = MagicMock(side_effect=lambda coro: asyncio.create_task(coro))
    return r


def _mk_runner_timed():
    """Runner stub with a real started_at timestamp for background-timeout paths."""
    from datetime import datetime, timezone

    r = MagicMock()
    r.session.status = "active"
    r.session.id = 1
    r.session.started_at = datetime.now(timezone.utc)
    r.agent.record_user_text = MagicMock()
    r.agent.cognitive_memory.working_memory.pending_probes = []
    r.agent.messages = [{"role": "assistant", "content": "Q"}]
    r.agent.current_phase.return_value.id = "p1"
    r.agent.agent_state = {"asked_questions": ["q"] * 12}
    r.agent.pace_message.return_value = None
    r.agent.record_assistant_text = MagicMock()
    r.agent.note_turn_output = MagicMock()
    r.agent.apply_plan_ops = MagicMock()
    r.agent.advance_phase_if_needed.return_value = False
    r.agent.save_state = MagicMock()
    r.agent.phase_title_for_display.return_value = "T"
    r.prompter.last_assistant_question.return_value = "Q"
    r.prompter.get_tech_domains.return_value = []
    r.prompter.build_user_content = MagicMock()
    r.prompter.get_context_window.return_value = 1000
    r.prompter.build_api_messages = AsyncMock(return_value=[{"role": "user", "content": "hi"}])
    r.tools.maybe_retrieve_rag = AsyncMock(return_value=None)
    r.llm = MagicMock(api_key="sk")
    r.spawn_bg_task = MagicMock(side_effect=lambda coro: asyncio.create_task(coro))
    return r


async def _collect(gen):
    """Drain an async event generator into a list for assertions."""
    return [e async for e in gen]

@pytest.mark.asyncio
async def test_completed_and_error_outcome():
    r = _mk_runner()
    r.session.status = "completed"
    evs = await _collect(stream_turn(r, "hi", MagicMock()))
    assert evs[0].kind == EventKind.ERROR and evs[0].error_code == "A2002"
    r2 = _mk_runner()
    async def _err(runner, outcome, msgs, db, temperature=0.75):
        outcome["error"] = RuntimeError("tool boom")
        if False:
            yield
    with patch("realmock.domains.interview.agents.interviewer.runner_turn.stream_tool_rounds", _err):
        evs2 = await _collect(stream_turn(r2, "hi", MagicMock()))
        assert evs2[-1].kind == EventKind.ERROR and evs2[-1].error_code == "C0001"


@pytest.mark.asyncio
async def test_regen_and_ledger_fail():
    r = _mk_runner()
    r.agent.agent_state = {"asked_questions": []}
    async def _empty(runner, outcome, msgs, db, temperature=0.75):
        from realmock.domains.interview.agents.tool_round_runner import ToolRoundResult
        outcome["value"] = ToolRoundResult(msgs, None)
        if False:
            yield
    async def _say(llm, tools, msgs, temperature=0.75):
        yield TurnOutput(say="regen answer", emotion="neutral", wait_seconds=5)
    with patch("realmock.domains.interview.agents.interviewer.runner_turn.stream_tool_rounds", _empty):
        with patch("realmock.domains.interview.agents.interviewer.runner_turn.stream_say_first", _say):
            with patch("realmock.domains.interview.agents.interviewer.runner_turn.maybe_fold_history", AsyncMock()):
                with patch("realmock.domains.interview.agents.interviewer.runner_turn.append_turn", side_effect=RuntimeError("db")):
                    evs = await _collect(stream_turn(r, "hi", MagicMock()))
                    assert evs[-1].kind == EventKind.ERROR
    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_bg_timeouts_do_not_block():
    r = _mk_runner()
    async def _empty2(runner, outcome, msgs, db, temperature=0.75):
        from realmock.domains.interview.agents.tool_round_runner import ToolRoundResult
        from realmock.domains.interview.agents.turn_output import TurnOutput as TO
        outcome["value"] = ToolRoundResult(msgs, None, streamed_output=TO(say="streamed", emotion="neutral"))
        if False:
            yield
    r.shadow_evaluator.evaluate_turn = AsyncMock(side_effect=asyncio.TimeoutError())
    with patch("realmock.domains.interview.agents.interviewer.runner_turn.stream_tool_rounds", _empty2):
        with patch("realmock.domains.interview.agents.interviewer.runner_turn.maybe_fold_history", AsyncMock()):
            with patch("realmock.domains.interview.agents.interviewer.runner_turn.append_turn", return_value=None):
                with patch("realmock.domains.interview.agents.interviewer.runner_turn.reflect_on_dialogue", AsyncMock(side_effect=asyncio.TimeoutError())):
                    evs = await _collect(stream_turn(r, "hi", MagicMock()))
                    assert any(e.kind == EventKind.TURN_COMPLETE for e in evs)
    await asyncio.sleep(0.2)
    for t in asyncio.all_tasks():
        if not t.done() and t is not asyncio.current_task():
            t.cancel()


@pytest.mark.asyncio
async def test_early_and_tool_yield_and_pace():
    r = _mk_runner_pace(qn=1)
    async def _tools(runner, outcome, msgs, db, temperature=0.75):
        from realmock.domains.interview.agents.tool_round_runner import ToolRoundResult
        assert msgs[0]["content"].startswith("[Pace:")
        outcome["value"] = ToolRoundResult(msgs, '{"say": "early hi", "v": 1}')
        yield StreamEvent.make_token("tool-tok")
    with patch("realmock.domains.interview.agents.interviewer.runner_turn.stream_tool_rounds", _tools):
        with patch("realmock.domains.interview.agents.interviewer.runner_turn.maybe_fold_history", AsyncMock()):
            with patch("realmock.domains.interview.agents.interviewer.runner_turn.append_turn", return_value=None):
                evs = await _collect(stream_turn(r, "hi", MagicMock()))
                assert any(e.token == "tool-tok" for e in evs if e.kind == EventKind.TOKEN)
                assert any(e.kind == EventKind.TURN_COMPLETE for e in evs)
    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_complete_triggers_finish_and_degraded():
    r = _mk_runner_pace()
    async def _empty(runner, outcome, msgs, db, temperature=0.75):
        from realmock.domains.interview.agents.tool_round_runner import ToolRoundResult
        outcome["value"] = ToolRoundResult(msgs, None)
        if False:
            yield
    async def _nosay(llm, tools, msgs, temperature=0.75):
        yield StreamEvent.make_token("tok")
        if False:
            yield  # pragma: no cover
    from realmock.domains.interview.agents.turn_output import TurnOutput
    done = TurnOutput(say="bye", interview_complete=True, verdict="passed", emotion="neutral")
    async def _say2(llm, tools, msgs, temperature=0.75):
        yield done
    with patch("realmock.domains.interview.agents.interviewer.runner_turn.stream_tool_rounds", _empty):
        with patch("realmock.domains.interview.agents.interviewer.runner_turn.stream_say_first", _nosay):
            with patch("realmock.domains.interview.agents.interviewer.runner_turn.maybe_fold_history", AsyncMock()):
                with patch("realmock.domains.interview.agents.interviewer.runner_turn.append_turn", return_value=None):
                    evs = await _collect(stream_turn(r, "hi", MagicMock()))
                    assert evs[-1].kind == EventKind.TURN_COMPLETE
    r2 = _mk_runner_pace()
    with patch("realmock.domains.interview.agents.interviewer.runner_turn.stream_tool_rounds", _empty):
        with patch("realmock.domains.interview.agents.interviewer.runner_turn.stream_say_first", _say2):
            with patch("realmock.domains.interview.agents.interviewer.runner_turn.maybe_fold_history", AsyncMock()):
                with patch("realmock.domains.interview.agents.interviewer.runner_turn.append_turn", return_value=None):
                    with patch("realmock.domains.interview.agents.interviewer.runner_turn.run_finish_lifecycle", return_value=None) as fl:
                        evs2 = await _collect(stream_turn(r2, "hi", MagicMock()))
                        assert evs2[-1].is_complete is True
                        assert fl.called
    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_fallback_and_generic_bg_errors():
    r = _mk_runner_timed()
    async def _noval(runner, outcome, msgs, db, temperature=0.75):
        yield __import__("realmock.domains.interview.agents.events", fromlist=["StreamEvent"]).StreamEvent.make_token("t")
    async def _say(llm, tools, msgs, temperature=0.75):
        from realmock.domains.interview.agents.turn_output import TurnOutput
        yield TurnOutput(say="ok", emotion="neutral")
    r.shadow_evaluator.evaluate_turn = AsyncMock(side_effect=RuntimeError("s fail"))
    with patch("realmock.domains.interview.agents.interviewer.runner_turn.stream_tool_rounds", _noval):
        with patch("realmock.domains.interview.agents.interviewer.runner_turn.stream_say_first", _say):
            with patch("realmock.domains.interview.agents.interviewer.runner_turn.maybe_fold_history", AsyncMock()):
                with patch("realmock.domains.interview.agents.interviewer.runner_turn.append_turn", return_value=None):
                    with patch("realmock.domains.interview.agents.interviewer.runner_turn.reflect_on_dialogue", AsyncMock(side_effect=RuntimeError("r fail"))):
                        r.process_orchestrator.decide_next_step = AsyncMock(side_effect=RuntimeError("o fail"))
                        evs = await _collect(stream_turn(r, "hi", MagicMock()))
                        assert any(e.kind == EventKind.TURN_COMPLETE for e in evs)
                        await asyncio.sleep(0.3)


@pytest.mark.asyncio
async def test_bg_timeouts_with_started_at():
    r = _mk_runner_timed()
    async def _empty(runner, outcome, msgs, db, temperature=0.75):
        from realmock.domains.interview.agents.tool_round_runner import ToolRoundResult
        from realmock.domains.interview.agents.turn_output import TurnOutput as TO
        outcome["value"] = ToolRoundResult(msgs, None, streamed_output=TO(say="s", emotion="neutral"))
        if False:
            yield
    r.shadow_evaluator.evaluate_turn = AsyncMock(side_effect=asyncio.TimeoutError())
    with patch("realmock.domains.interview.agents.interviewer.runner_turn.stream_tool_rounds", _empty):
        with patch("realmock.domains.interview.agents.interviewer.runner_turn.maybe_fold_history", AsyncMock()):
            with patch("realmock.domains.interview.agents.interviewer.runner_turn.append_turn", return_value=None):
                with patch("realmock.domains.interview.agents.interviewer.runner_turn.reflect_on_dialogue", AsyncMock(side_effect=asyncio.TimeoutError())):
                    r.process_orchestrator.decide_next_step = AsyncMock(side_effect=asyncio.TimeoutError())
                    evs = await _collect(stream_turn(r, "hi", MagicMock()))
                    assert any(e.kind == EventKind.TURN_COMPLETE for e in evs)
                    await asyncio.sleep(0.3)

