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
from realmock.domains.interview.agents.agent_policies import BACKGROUND
from realmock.domains.interview.agents.events import LedgerWriteError, StreamEvent
from realmock.platform.core.agent_error_log import log_agent_error
from realmock.domains.interview.agents.finish_lifecycle import run_finish_lifecycle
from realmock.domains.interview.agents.followup_inject import build_turn_guidance
from realmock.domains.interview.agents.step_compaction import (
    spawn_boundary_compaction,
)
from realmock.domains.interview.agents.say_first import (
    parse_complete_output,
    stream_say_first,
)
from realmock.domains.interview.agents.tool_round_runner import ToolRoundResult
from realmock.domains.interview.agents.tool_round_stream import stream_tool_rounds
from realmock.domains.interview.agents.turn_output import TurnOutput, parse_turn_output
from realmock.platform.capabilities.ai.agent.loop import build_environment_hint

if TYPE_CHECKING:
    from realmock.domains.interview.agents.interviewer.runner import InterviewRunner

logger = logging.getLogger(__name__)


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
        guidance_blocks = build_turn_guidance(
            runner.agent,
            user_text=user_text,
            last_question=last_question,
            tech_domains=runner.prompter.get_tech_domains(db),
            phase_id=runner.agent.current_phase().id,
            rag_msg=rag_msg,
            session_id=runner.session.id,
            pending_probe=pending_probe,
        )

        context_window = runner.prompter.get_context_window(db)
        step_msg = runner.agent.step_message()
        pace_msg = runner.agent.pace_message()
        api_messages = await runner.prompter.build_api_messages(
            user_text, face, image_b64, context_window=context_window
        )
        # Everything below rides the TRANSIENT tail (after the last user
        # message — the same slot the platform loop uses for [Context]/
        # [Budget]) and is rebuilt from state every call, never persisted:
        # persisting per-turn guidance resurfaced it on every later turn,
        # and a per-turn head rewrite would invalidate the provider prefix
        # cache for the whole frozen system head.
        tail: list[dict[str, Any]] = list(guidance_blocks)
        memory_block = runner.agent.memory_block()
        if memory_block:
            tail.append({"role": "system", "content": memory_block})
        if not image_b64 and isinstance(face, dict) and face:
            # Face hints ride the call copy only; the persisted user text
            # stays clean ("candidate appears nervous" must not haunt turn 30).
            hinted = runner.prompter.build_user_content(user_text, face)
            if hinted != user_text:
                for message in reversed(api_messages):
                    if message.get("role") == "user":
                        message["content"] = hinted
                        break
        # Position/Pace: their text changes every turn; prepending them would
        # shift the entire frozen head one position per turn and punch through
        # the prefix cache. On image turns build_api_messages already embedded
        # the face hints in the multimodal user content.
        suffix = step_msg if not pace_msg else f"{step_msg}\n{pace_msg}"
        if suffix:
            tail.append({"role": "system", "content": suffix})
        api_messages.extend(tail)

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

        output: TurnOutput | None
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
            # Same-turn regeneration bypasses the loop, so it would miss the
            # [Context] environment anchor every loop round carries — append
            # it here to keep the model/date grounding consistent.
            regen_messages = [*result.messages, build_environment_hint(runner.llm)]
            async for item in stream_say_first(
                runner.llm, runner.tools, regen_messages, temperature=0.75
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
        # Snapshot before the advance: a phase advance appends the NEXT step's
        # entry message, and that message belongs to the new step's segment —
        # a boundary spanning it would let the compactor splice the new step's
        # instructions (reverse_qa role switch, summary trajectory) out of the
        # live context.
        boundary_end = len(runner.agent.messages)
        phase_changed = runner.agent.advance_phase_if_needed(
            output.say, phase_complete=output.phase_complete
        )

        if output.interview_complete:
            runner.agent.note_verdict(output.verdict)
            runner.agent.mark_completed()
        tools = take_pending_tools(runner.agent.agent_state)
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
        except Exception as e:
            logger.exception(
                "ledger append_turn failed sid=%s",
                getattr(runner.session, "id", None),
            )
            raise LedgerWriteError("ledger append failed") from e

        # Background agent (never gates the reply): the shadow evaluator
        # assesses the turn and feeds the cognitive graph. Bounded by a
        # timeout so a slow LLM cannot pile up tasks or starve the main
        # loop's rate budget.
        turn_index = len(runner.agent.agent_state.get("asked_questions", []))

        async def _bounded_shadow() -> None:
            try:
                await asyncio.wait_for(
                    runner.shadow_evaluator.evaluate_turn(
                        question=last_question,
                        user_text=user_text,
                        current_phase=turn_phase,
                        turn_index=turn_index,
                        step_focus=runner.agent.current_phase().description,
                    ),
                    timeout=BACKGROUND.shadow_seconds,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "shadow evaluation timed out sid=%s turn=%s",
                    getattr(runner.session, "id", None),
                    turn_index,
                )
            except Exception:
                logger.debug("background shadow evaluation failed", exc_info=True)

        # Step boundary: the interviewer closed a step — the background
        # compactor turns its verbatim dialogue into a structured brief.
        boundary = None
        if phase_changed:
            boundary = runner.agent.mark_step_boundary(end=boundary_end)
        try:
            runner.spawn_bg_task(_bounded_shadow())
            if boundary is not None:
                spawn_boundary_compaction(runner, boundary)
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
            answer_wait_seconds=output.answer_wait_seconds,
            sources=output.sources,
            result=output.verdict if output.interview_complete else None,
            phase_title=runner.agent.phase_title_for_display(),
        )
    except LedgerWriteError:
        # The answer was already streamed; only the record is missing.
        # Distinct code + actionable copy (front-end toasts the message).
        log_agent_error(
            domain="interview",
            session=str(getattr(runner.session, "id", "")),
            kind="ledger_write_failed",
            message="runner_turn: ledger append failed after streaming",
        )
        yield StreamEvent.make_error(
            "Your answer was generated but could not be saved; please retry, or export the transcript from the report page.",
            code="C0003",
            retryable=False,
        )
    except Exception as e:
        logger.exception("Round execution failed: %s", e)
        yield StreamEvent.make_error(
            "AI interviewer temporarily unavailable; please retry later",
            code="C0001",
            retryable=True,
        )
