"""Regular turn stream (InterviewRunner child): candidate reply → streamed events.

Face / follow-up injection: :mod:`followup_inject`. Context assembly:
:mod:`prompt_assembler`. Appends a ledger turn after a successful reply.
Tool-round speculative tokens stream live through a bounded queue while the
tool loop runs (produce/consume bridge, mirroring the prep chat pattern).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from realmock.domains.interview.ledger.store import append_turn, take_pending_tools
from realmock.domains.interview.services.interview.events import StreamEvent
from realmock.domains.interview.services.interview.finish_lifecycle import run_finish_lifecycle
from realmock.domains.interview.services.interview.followup_inject import append_followup_and_rag
from realmock.domains.interview.services.interview.say_first import (
    parse_complete_output,
    stream_say_first,
)
from realmock.domains.interview.services.interview.tool_round_runner import ToolRoundResult
from realmock.domains.interview.services.interview.tool_round_stream import stream_tool_rounds
from realmock.domains.interview.services.interview.turn_output import TurnOutput, parse_turn_output

if TYPE_CHECKING:
    from realmock.domains.interview.services.interview.runner import InterviewRunner

logger = logging.getLogger(__name__)

# Bound on in-flight speculative tokens: backpressure when the WS consumer
# lags instead of unbounded growth (mirrors the prep event queue).


async def stream_turn(
    runner: "InterviewRunner",
    user_text: str,
    db: Session,
    *,
    face: dict[str, Any] | None = None,
    image_b64: str | None = None,
    followup_probe: str | None = None,
) -> AsyncIterator[StreamEvent]:
    """Process candidate responses and output streaming events."""
    if runner.session.status == "completed":
        yield StreamEvent.make_error("Interview already finished", code="A2002")
        return

    try:
        runner.agent.record_user_text(user_text)

        last_question = runner.prompter.last_assistant_question()
        rag_msg = await runner.tools.maybe_retrieve_rag(
            query=f"{last_question} {user_text}".strip(),
        )
        append_followup_and_rag(
            runner.agent,
            user_text=user_text,
            last_question=last_question,
            tech_domains=runner.prompter.get_tech_domains(db),
            phase_id=runner.agent.current_phase().id,
            rag_msg=rag_msg,
            face=face,
            build_user_content=runner.prompter.build_user_content,
            session_id=runner.session.id,
        )

        context_window = runner.prompter.get_context_window(db)
        api_messages = await runner.prompter.build_api_messages(
            user_text, face, image_b64, context_window=context_window
        )

        outcome: dict[str, Any] = {}
        async for event in stream_tool_rounds(runner, outcome, api_messages, db, temperature=0.75):
            yield event
        error = outcome.get("error")
        if error is not None:
            # Business/orchestration failures surface as an SSE error event —
            # never degrade into a silent regeneration (run_chat contract).
            raise error
        result = outcome.get("value")
        if not isinstance(result, ToolRoundResult):
            result = ToolRoundResult(api_messages, None)

        output: TurnOutput
        if result.streamed_output is not None:
            # Say tokens already streamed live during the tool loop; reuse the
            # streamed turn's control fields without re-emitting the text.
            output = result.streamed_output
        elif result.early:
            output = parse_complete_output(result.early)
            if output.say:
                yield StreamEvent.make_token(output.say)
        else:
            output = None
            async for item in stream_say_first(
                runner.llm, runner.tools, result.messages, temperature=0.75
            ):
                if isinstance(item, TurnOutput):
                    output = item
                else:
                    yield item
            output = output or parse_turn_output(None, say_text="", degraded=True)

        runner.agent.record_assistant_text(output.say)
        runner.agent.note_turn_output(output)
        turn_phase = runner.agent.current_phase().id
        # Dynamic flow maintenance first: an inserted step right after the
        # current one becomes the next current step when phase_complete follows.
        runner.agent.apply_plan_ops(output.plan_ops)
        phase_changed = runner.agent.advance_phase_if_needed(
            output.say, phase_complete=output.phase_complete
        )

        if output.interview_complete:
            runner.agent.note_verdict(output.verdict)
            runner.agent.mark_completed()
        tools = take_pending_tools(runner.agent.agent_state)
        runner.agent.save_state(db)

        try:
            append_turn(
                db,
                runner.session,
                phase=turn_phase,
                assistant_text=output.say or "",
                user_text=user_text,
                user_source="text",
                tools=tools,
            )
        except Exception:
            logger.exception(
                "ledger append_turn failed sid=%s",
                getattr(runner.session, "id", None),
            )
            raise

        if output.interview_complete:
            run_finish_lifecycle(db, runner.session, mark_completed=False)

        yield StreamEvent.make_turn_done(
            content=output.say,
            phase_id=runner.agent.current_phase().id,
            is_complete=output.interview_complete,
            phase_changed=phase_changed,
            emotion=output.emotion,
            wait_seconds=output.wait_seconds,
            sources=output.sources,
            result=output.verdict if output.interview_complete else None,
            phase_title=runner.agent.phase_title_for_display(),
        )
    except Exception as e:
        logger.exception("Round execution failed: %s", e)
        yield StreamEvent.make_error("AI interviewer temporarily unavailable; please retry later", code="C0001", retryable=True)
