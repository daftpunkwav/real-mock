"""Regular turn stream (InterviewRunner child): candidate reply → streamed events.

Face / follow-up injection: :mod:`followup_inject`. Context assembly:
:mod:`prompt_assembler`. Appends a ledger turn after a successful reply.
Tool-round speculative tokens stream live through a bounded queue while the
tool loop runs (produce/consume bridge, mirroring the prep chat pattern).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from realmock.domains.interview.ledger.store import append_turn, take_pending_tools
from realmock.domains.interview.agents.events import StreamEvent
from realmock.domains.interview.agents.finish_lifecycle import run_finish_lifecycle
from realmock.domains.interview.agents.followup_inject import append_followup_and_rag
from realmock.domains.interview.agents.history_compaction import maybe_fold_history
from realmock.domains.interview.agents.memory.reflection import reflect_on_dialogue
from realmock.domains.interview.agents.say_first import (
    parse_complete_output,
    stream_say_first,
)
from realmock.domains.interview.agents.tool_round_runner import ToolRoundResult
from realmock.domains.interview.agents.tool_round_stream import stream_tool_rounds
from realmock.domains.interview.agents.turn_output import TurnOutput, parse_turn_output

if TYPE_CHECKING:
    from realmock.domains.interview.agents.runner import InterviewRunner

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
        pending_probe = None
        if runner.agent.cognitive_memory.working_memory.pending_probes:
            pending_probe = runner.agent.cognitive_memory.working_memory.pending_probes.pop(0)

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
            pending_probe=pending_probe,
        )

        context_window = runner.prompter.get_context_window(db)
        pace_msg = runner.agent.pace_message()
        api_messages = await runner.prompter.build_api_messages(
            user_text, face, image_b64, context_window=context_window
        )
        # Pace is a transient, one-shot hint for this LLM call only. Do not
        # persist it in message history: it would make messages[-1] a system
        # message and break the "user message is last" invariant, and on
        # image turns it would be replaced by the multimodal user content.
        if pace_msg:
            api_messages = [{"role": "system", "content": pace_msg}, *api_messages]

        outcome: dict[str, Any] = {}
        t_tools = time.perf_counter()
        async for event in stream_tool_rounds(runner, outcome, api_messages, db, temperature=0.75):
            yield event
        tools_ms = (time.perf_counter() - t_tools) * 1000.0
        error = outcome.get("error")
        if error is not None:
            # Business/orchestration failures surface as an SSE error event —
            # never degrade into a silent regeneration (run_chat contract).
            raise error
        result = outcome.get("value")
        if not isinstance(result, ToolRoundResult):
            result = ToolRoundResult(api_messages, None)

        output: TurnOutput
        t_say = time.perf_counter()
        say_mode = "streamed"
        if result.streamed_output is not None:
            # Say tokens already streamed live during the tool loop; reuse the
            # streamed turn's control fields without re-emitting the text.
            output = result.streamed_output
        elif result.early:
            say_mode = "early"
            output = parse_complete_output(result.early)
            if output.say:
                yield StreamEvent.make_token(output.say)
        else:
            say_mode = "regenerated"
            output = None
            async for item in stream_say_first(
                runner.llm, runner.tools, result.messages, temperature=0.75
            ):
                if isinstance(item, TurnOutput):
                    output = item
                else:
                    yield item
            output = output or parse_turn_output(None, say_text="", degraded=True)
        say_ms = (time.perf_counter() - t_say) * 1000.0
        logger.info(
            "turn_llm sid=%s tools_ms=%.0f say_ms=%.0f say_mode=%s",
            getattr(runner.session, "id", None),
            tools_ms,
            say_ms,
            say_mode,
        )

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
        # Persist the history fold before save_state so the DB row stops
        # growing once past half the context window (ledger keeps verbatim).
        await maybe_fold_history(runner.agent, llm=runner.llm, context_window=context_window)
        runner.agent.save_state(db)

        try:
            ts = output.turn_score
            score_flags = (
                {
                    "turn_score": {
                        "brief": ts.brief,
                        "rating": ts.rating,
                        "weak_points": list(ts.weak_points),
                    }
                }
                if ts is not None
                else None
            )
            append_turn(
                db,
                runner.session,
                phase=turn_phase,
                assistant_text=output.say or "",
                user_text=user_text,
                user_source="text",
                tools=tools,
                flags=score_flags,
            )
        except Exception:
            logger.exception(
                "ledger append_turn failed sid=%s",
                getattr(runner.session, "id", None),
            )
            raise

        # Background agents (never gate the reply): Shadow evaluates the turn,
        # periodic reflection consolidates memory, and the Process Orchestrator
        # advises macro pacing. Each is bounded by a timeout so a slow LLM
        # cannot pile up tasks or starve the main loop's rate budget.
        turn_index = len(runner.agent.agent_state.get("asked_questions", []))

        async def _bounded_shadow() -> None:
            try:
                await asyncio.wait_for(
                    runner.shadow_evaluator.evaluate_turn(
                        question=last_question,
                        user_text=user_text,
                        current_phase=turn_phase,
                        turn_index=turn_index,
                    ),
                    timeout=45.0,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "shadow evaluation timed out sid=%s turn=%s",
                    getattr(runner.session, "id", None),
                    turn_index,
                )
            except Exception:
                logger.debug("background shadow evaluation failed", exc_info=True)

        async def _bounded_reflection() -> None:
            try:
                recent_turns = [
                    {"assistant": m.get("content", ""), "user": user_text}
                    for m in runner.agent.messages[-4:]
                    if isinstance(m, dict)
                ]
                await asyncio.wait_for(
                    reflect_on_dialogue(
                        runner.llm,
                        runner.agent.cognitive_memory,
                        recent_turns,
                        turn_index,
                    ),
                    timeout=60.0,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "reflection timed out sid=%s turn=%s",
                    getattr(runner.session, "id", None),
                    turn_index,
                )
            except Exception:
                logger.debug("background reflection failed", exc_info=True)

        async def _bounded_orchestrator() -> None:
            try:
                from datetime import datetime, timezone as _tz

                from realmock.domains.interview.agents.topology.process_orchestrator import (
                    OrchestrationDirective,
                )

                started = getattr(runner.session, "started_at", None)
                now = datetime.now(_tz.utc)
                if started is not None:
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=_tz.utc)
                    elapsed_minutes = max(0.0, (now - started).total_seconds() / 60.0)
                else:
                    elapsed_minutes = float(turn_index * 2)
                advice = await asyncio.wait_for(
                    runner.process_orchestrator.decide_next_step(
                        current_phase=turn_phase,
                        turn_index=turn_index,
                        elapsed_minutes=elapsed_minutes,
                    ),
                    timeout=20.0,
                )
                # Advisory only: persisted for observability, never gates reply.
                runner.agent.agent_state["_orchestrator_advice"] = {
                    "directive": advice.directive.value
                    if isinstance(advice.directive, OrchestrationDirective)
                    else str(advice.directive),
                    "reason": advice.reason,
                    "target_topic": advice.target_topic,
                    "turn_index": turn_index,
                }
            except asyncio.TimeoutError:
                logger.warning(
                    "orchestrator advice timed out sid=%s turn=%s",
                    getattr(runner.session, "id", None),
                    turn_index,
                )
            except Exception:
                logger.debug("background orchestrator advice failed", exc_info=True)

        try:
            asyncio.create_task(_bounded_shadow())
            if turn_index > 0 and turn_index % 4 == 0:
                asyncio.create_task(_bounded_reflection())
            if turn_index > 0 and turn_index % 6 == 0:
                asyncio.create_task(_bounded_orchestrator())
        except Exception:
            logger.debug("background agent trigger failed", exc_info=True)

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
