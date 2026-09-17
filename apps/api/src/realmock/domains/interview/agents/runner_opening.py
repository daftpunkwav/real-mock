"""Opening stream (InterviewRunner child): start interview and stream greeting.

Says-first parsing and tool rounds: :mod:`say_first` / :mod:`tool_round_runner`.
Appends an assistant-only ledger turn after a successful opening.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from realmock.domains.interview.ledger.store import append_turn, take_pending_tools
from realmock.domains.interview.agents.events import StreamEvent
from realmock.domains.interview.agents.history_compaction import maybe_fold_history
from realmock.domains.interview.agents.say_first import (
    parse_complete_output,
    stream_say_first,
)
from realmock.domains.interview.agents.tool_round_runner import ToolRoundResult
from realmock.domains.interview.agents.tool_round_stream import stream_tool_rounds
from realmock.domains.interview.agents.turn_output import TurnOutput, parse_turn_output
from realmock.domains.interview.agents.planning.planner import ensure_plan

if TYPE_CHECKING:
    from realmock.domains.interview.agents.runner import InterviewRunner

logger = logging.getLogger(__name__)


async def stream_opening(runner: "InterviewRunner", db: Session) -> AsyncIterator[StreamEvent]:
    """Start the interview and return to the streaming opening."""
    try:
        # Bounded wait for the background flow planner; degrades to the static
        # workflow as a fallback plan when the planner failed or timed out.
        await ensure_plan(db, runner.session)
        runner.agent.reload_plan()

        runner.agent.reset_messages()
        system_prompt = runner.agent.build_opening_prompt(db)
        runner.agent.messages = [{"role": "system", "content": system_prompt}]
        context_window = runner.prompter.get_context_window(db)
        if context_window:
            from realmock.platform.capabilities.ai.context.manager import compress_messages

            runner.agent.messages = compress_messages(runner.agent.messages, context_window)

        opening_messages = list(runner.agent.messages) + [
            {"role": "user", "content": "The interview is starting; begin asking questions for the current phase."},
        ]
        outcome: dict[str, Any] = {}
        async for event in stream_tool_rounds(runner, outcome, opening_messages, db, temperature=0.8):
            yield event
        error = outcome.get("error")
        if error is not None:
            raise error
        result = outcome.get("value")
        if not isinstance(result, ToolRoundResult):
            result = ToolRoundResult(opening_messages, None)

        output: TurnOutput
        if result.streamed_output is not None:
            # Say tokens already streamed live during the tool loop.
            output = result.streamed_output
        elif result.early:
            # Tool wheel text answers also follow the protocol and are parsed first and then distributed.
            output = parse_complete_output(result.early)
            if output.say:
                yield StreamEvent.make_token(output.say)
        else:
            output = None
            async for item in stream_say_first(
                runner.llm, runner.tools, result.messages, temperature=0.8
            ):
                if isinstance(item, TurnOutput):
                    output = item
                else:
                    yield item
            output = output or parse_turn_output(None, say_text="", degraded=True)

        runner.agent.record_assistant_text(output.say)
        runner.agent.note_turn_output(output)
        runner.agent.set_questions_in_phase(1)
        runner.agent.mark_active()
        tools = take_pending_tools(runner.agent.agent_state)
        await maybe_fold_history(runner.agent, llm=runner.llm, context_window=context_window)
        runner.agent.save_state(db)

        try:
            append_turn(
                db,
                runner.session,
                phase=runner.agent.current_phase().id,
                assistant_text=output.say or "",
                tools=tools,
            )
        except Exception:
            logger.exception(
                "ledger append_turn failed on opening sid=%s",
                getattr(runner.session, "id", None),
            )
            raise

        # Opening does not advance on question caps; only explicit phase_complete.
        if output.phase_complete:
            runner.agent.advance_phase_if_needed(output.say, phase_complete=True)

        yield StreamEvent.make_turn_done(
            content=output.say,
            phase_id=runner.agent.current_phase().id,
            is_complete=output.interview_complete,
            phase_changed=output.phase_complete,
            emotion=output.emotion,
            wait_seconds=output.wait_seconds,
            answer_wait_seconds=output.answer_wait_seconds,
            sources=output.sources,
            phase_title=runner.agent.phase_title_for_display(),
        )
    except Exception as e:
        logger.exception("Opening round failed: %s", e)
        yield StreamEvent.make_error("AI interviewer temporarily unavailable; please retry later", code="C0001", retryable=True)
