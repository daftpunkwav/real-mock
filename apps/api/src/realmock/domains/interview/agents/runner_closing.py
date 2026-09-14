"""Closing stream (InterviewRunner child): verbal thanks + personalized wrap-up.

Closing prompts: :mod:`closing_prompts`. After save_state, freezes ledger and
notifies platform lifecycle hooks (report generation remains dual-track elsewhere).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from realmock.domains.interview.ledger.store import append_turn, take_pending_tools
from realmock.domains.interview.agents.closing_prompts import (
    CLOSING_BY_PERSONALITY,
    closing_system_prompt,
    jump_to_summary_phase,
)
from realmock.domains.interview.agents.events import StreamEvent
from realmock.domains.interview.agents.finish_lifecycle import run_finish_lifecycle
from realmock.domains.interview.agents.history_compaction import maybe_fold_history
from realmock.domains.interview.agents.say_first import stream_say_first
from realmock.domains.interview.agents.turn_output import TurnOutput, parse_turn_output

if TYPE_CHECKING:
    from realmock.domains.interview.agents.runner import InterviewRunner

logger = logging.getLogger(__name__)


async def stream_closing(runner: "InterviewRunner", db: Session) -> AsyncIterator[StreamEvent]:
    """The candidate ends on his own initiative: the interviewer verbally thanks him + a personalized summary, and marks the interview as complete."""
    if runner.session.status == "completed":
        yield StreamEvent.make_error("Interview already finished", code="A2002")
        return

    try:
        personality = (runner.session.personality or "professional").lower()
        style_hint = CLOSING_BY_PERSONALITY.get(
            personality, CLOSING_BY_PERSONALITY["professional"]
        )
        jump_to_summary_phase(runner.agent, [p.id for p in runner.agent.phases])
        runner.agent.messages.append(
            {"role": "system", "content": closing_system_prompt(style_hint)}
        )
        runner.agent.refresh_system_memory()

        context_window = runner.prompter.get_context_window(db)
        api_messages = list(runner.agent.messages)
        if context_window:
            from realmock.platform.capabilities.ai.context.summarize import compact_with_summary

            # Closing sees the whole conversation: LLM minutes keep the wrap-up
            # grounded for long interviews; rule-based compaction degrades safely.
            api_messages = await compact_with_summary(
                api_messages, context_window, llm=runner.llm, keep_recent=24
            )
        api_messages = api_messages + [
            {"role": "user", "content": "(system) Complete the spoken wrap-up and evaluation as instructed."},
        ]

        output: TurnOutput | None = None
        say_parts: list[str] = []
        async for item in stream_say_first(
            runner.llm, runner.tools, api_messages, temperature=0.7
        ):
            if isinstance(item, TurnOutput):
                output = item
            else:
                say_parts.append(item.token)
                yield item
        output = output or parse_turn_output(
            None, say_text="".join(say_parts), degraded=True
        )
        # Completed at the end: When the model is leaked to interview_complete, it is set by the server.
        if output.interview_complete is False:
            output = replace(output, interview_complete=True)

        runner.agent.record_assistant_text(output.say)
        runner.agent.note_turn_output(output)
        runner.agent.note_verdict(output.verdict)
        runner.agent.mark_completed()
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
                "ledger append_turn failed on closing sid=%s",
                getattr(runner.session, "id", None),
            )
            raise

        run_finish_lifecycle(db, runner.session, mark_completed=False)

        yield StreamEvent.make_turn_done(
            content=output.say,
            phase_id=runner.agent.current_phase().id,
            is_complete=True,
            phase_changed=True,
            emotion=output.emotion or "smile",
            wait_seconds=output.wait_seconds,
            sources=output.sources,
            result=output.verdict,
            phase_title=runner.agent.phase_title_for_display(),
        )
    except Exception as e:
        logger.exception("Closing speech failed: %s", e)
        yield StreamEvent.make_error("AI interviewer temporarily unavailable; please retry later", code="C0001", retryable=True)
