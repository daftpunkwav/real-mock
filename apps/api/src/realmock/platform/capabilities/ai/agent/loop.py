"""Unified Agent loop: one step = one LLM call + this round's tool execution.

Aligned with the step in Pi ``agentLoop`` / DeepSeek Harness (model request + tools it calls).
Domain tools register with an OpenAI tools schema + ``execute`` callback (a minimal form of the Harness principle "capabilities are plugins"),
without introducing Cordis, MCP, shell, or sub-Agents.

Layered by responsibility:
- ``loop.py``: main ``run_agent_loop`` orchestration and result structures;
- ``llm_round.py``: one LLM round (streaming preferred) and tool-result truncation;
- ``hints.py``: closing/correction hint constants; ``halt.py``: the ``AgentHalt`` termination signal.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from realmock.platform.capabilities.ai.llm.tool_args import parse_tool_arguments
from realmock.platform.core.agent_error_log import error_scope, log_agent_error
from realmock.platform.core.errors import ApiBusinessError

from .halt import AgentHalt
from .hints import _DRIFT_HINT, _DRIFT_MAX_CHARS, _WRAP_UP_HINT, countdown_hint
from .llm_round import (
    ExecuteFn,
    OnThinkFn,
    OnTextFn,
    OnToolFn,
    _call_llm_round,
    _truncate_tool_result,
)

logger = logging.getLogger(__name__)


def _join_thinking(parts: list[str]) -> str:
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


@dataclass
class LoopResult:
    """The result of one or more tool cycles."""

    messages: list[dict[str, Any]]
    final_content: str | None
    tool_used: bool
    halted: bool = False
    # Reasoning from every round, joined for display only; empty when the
    # provider does not return any.
    thinking: str = ""
    extras: dict[str, Any] = field(default_factory=dict)


async def run_agent_loop(
    llm: Any,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None,
    execute: ExecuteFn,
    max_rounds: int,
    max_tools_per_round: int = 8,
    temperature: float = 0.7,
    on_tool: OnToolFn | None = None,
    on_thinking: OnThinkFn | None = None,
    on_content: OnTextFn | None = None,
    on_round_start: Callable[[], Awaitable[None]] | None = None,
    drift_retry: bool = False,
    wrap_up_hint: dict[str, Any] | None = None,
    prepare_messages: Callable[[list[dict[str, Any]]], Awaitable[list[dict[str, Any]]]] | None = None,
    compact_observation: Callable[[str], Awaitable[str]] | None = None,
    error_context: dict[str, Any] | None = None,
    countdown_rounds: int = 0,
    round_retries: int = 0,
    final_round_tool_free: bool = False,
) -> LoopResult:
    """Execute the tool loop until the model stops requesting tools or ``max_rounds`` is reached.

    As soon as the model returns body text without tool_calls, that body is the final answer (whether or not
    tools were used earlier)—the loop ends and the caller speaks it directly, without a second tool-free generation (matching terminal
    Agent closing semantics: the model stops acting = the turn ends).
    If, after tools were called, the model returns only tool_calls and reaches ``max_rounds``: ``final_content``
    is None, and the caller may generate a closing answer. Multiple tools in the same round execute in parallel (results are
    filled back in tool_calls order, preserving message pairing). Calls beyond ``max_tools_per_round`` stay
    declared in the assistant message and receive an explicit "not executed" observation, so protocol
    pairing holds and the model knows the budget cut them.

    ``on_thinking``: real-time callback for model reasoning—the LLM call in each round prefers
    streaming ``chat_message_stream`` (reasoning deltas are immediately visible, avoiding a silent connection during long reasoning);
    when the client lacks it or the protocol does not support it, fall back to non-streaming (reasoning is delivered once with the message);
    ``on_content``: optional real-time callback for raw body-text deltas (speculative streaming).
    Deltas only flow once the first tool round has completed: a pre-tool content round may
    still be drift-retried, so its text stays buffered and reaches the display through the
    caller's replay path instead. Callers must still treat every delta as provisional until
    the round completes; ``prepare_messages``: optional per-round context rewrite (LLM compression, memory inject).
    ``compact_observation``: optional per-tool-result rewrite; when omitted, observations are
    hard-capped with an explicit truncation marker.
    ``wrap_up_hint``: last-round system reminder; defaults to the shared wrap-up copy.
    ``error_context``: optional ``{"domain": ..., "session": ...}`` attached to
    persisted agent-error records (see ``platform.core.agent_error_log``).
    ``drift_retry``: when True, a pre-tool text-only round that merely
    narrates an action ("I will now search...") instead of working gets a
    one-shot correction hint and an immediate retry; only the first such
    round is corrected, and the last round is exempt (it must return text).
    ``countdown_rounds``: size of the soft-landing window before the round cap.
    Rounds that still have 1..countdown_rounds rounds after them (except the
    last, which gets ``wrap_up_hint``) receive a transient countdown nudge —
    advisory in the outer half ("conclude evidence gathering"), urgent in the
    inner half ("no new explorations, output the final answer").
    ``round_retries``: how many times a failed round LLM call is retried
    (bounded); 0 keeps the fail-fast behavior.
    ``final_round_tool_free``: when True, the last round's request omits the
    tools parameter entirely, so the model can only answer with text — a
    protocol-level guarantee of a final answer instead of an advisory hint the
    model can ignore. The caller's ``wrap_up_hint`` copy should match (no
    "call only one tool" phrasing).

    Error contract: :class:`AgentHalt` ends the loop with its observation;
    :class:`ApiBusinessError` raised by ``execute`` propagates to the caller
    (business failures must not be disguised as model observations); any other
    tool exception becomes a ``"Tool execution failed: ..."`` observation.
    """
    if not tools or max_rounds <= 0:
        return LoopResult(messages=list(messages), final_content=None, tool_used=False)

    closing_hint = wrap_up_hint if wrap_up_hint is not None else _WRAP_UP_HINT
    working = list(messages)
    tool_used = False
    halted = False
    thinking_parts: list[str] = []
    thinking_emitted = False
    drift_corrected = False
    # Holding area for one-shot reminders (correction / closing): visible
    # only to the next LLM call, never persisted to working.
    transient: list[dict[str, Any]] = []

    for round_i in range(max_rounds):
        if on_round_start is not None:
            # Round boundary: lets per-round stateful consumers (protocol
            # parsers, stream filters) reset before the next LLM call.
            await on_round_start()
        call_messages = list(working)
        is_last_round = round_i == max_rounds - 1
        if prepare_messages is not None:
            call_messages = await prepare_messages(call_messages)
        # Transient hints (one-call correction / closing prompt) are injected
        # after prepare_messages, for the same reason as the countdown nudge
        # below: domain rewrites (LLM compaction) hoist system-role messages
        # to the stable head, which would bury these one-call nudges far from
        # the generation point instead of at the strongest attention position.
        call_messages.extend(transient)
        transient = []
        # Inject the closing hint on the last round (visible only to this
        # call; never persisted to working).
        if is_last_round and round_i > 0:
            call_messages.append(closing_hint)
        # The countdown nudge is injected after prepare_messages: its text
        # changes every round, so placing it before the prepare hook would let
        # domain context rewrites move it into the stable head and punch
        # through the provider prefix cache. As a transient suffix it also
        # sits at the strongest attention position.
        if countdown_rounds > 0 and not is_last_round:
            remaining_rounds = max_rounds - round_i - 1
            if 0 < remaining_rounds <= countdown_rounds:
                urgent = remaining_rounds <= max(1, countdown_rounds // 2)
                call_messages.append(countdown_hint(remaining_rounds, urgent=urgent))

        round_thinking: list[str] = []

        async def emit_thinking(text: str) -> None:
            nonlocal thinking_emitted
            if not text:
                return
            # Display channel: the inter-round separator is prepended only at
            # the first segment of a new round; round_thinking keeps the
            # original segments.
            display = ("\n\n" + text) if (thinking_emitted and not round_thinking) else text
            thinking_emitted = True
            round_thinking.append(text)
            if on_thinking is not None:
                maybe = on_thinking(display)
                if maybe is not None and inspect.isawaitable(maybe):
                    await maybe

        # Tool-free final round: without a tools parameter the model can only
        # answer with text, so the cap produces a real answer instead of
        # another round of tool calls that ignores the advisory hint.
        round_tools = None if (final_round_tool_free and is_last_round) else tools

        async def call_round_llm() -> dict[str, Any]:
            # Speculative content streaming only after the first tool round: a
            # pre-tool content round may still be drift-retried (its text would
            # then be generated twice), so pre-tool text stays buffered and
            # reaches the display through the caller's replay path. After tools
            # have run, a content-only round is always the final answer.
            emit_content = on_content if (on_content is not None and tool_used) else None
            return await _call_llm_round(
                llm,
                call_messages,
                temperature=temperature,
                tools=round_tools,
                emit_thinking=emit_thinking,
                emit_content=emit_content,
            )

        msg: dict[str, Any] | None = None
        attempts_left = 1 + max(0, round_retries)
        while attempts_left > 0:
            attempts_left -= 1
            try:
                msg = await call_round_llm()
                break
            except Exception as e:
                if attempts_left == 0:
                    logger.warning(
                        "Agent round LLM failed round=%s: %s: %s",
                        round_i, type(e).__name__, e,
                    )
                    domain, session = error_scope(error_context)
                    log_agent_error(
                        domain=domain, session=session, kind="llm_round_failed",
                        message=f"round {round_i}: {e}",
                    )
                    break
                # A failed mid-stream attempt may have already emitted partial
                # reasoning deltas; drop them so the retry forms one clean
                # thinking segment instead of duplicating the head.
                round_thinking.clear()
                logger.warning(
                    "Agent round LLM call failed (%s: %s); retrying round=%s",
                    type(e).__name__, e, round_i,
                )
        if msg is None:
            break

        if not round_thinking:
            # Non-streaming path: reasoning arrives once with the message;
            # emit it here.
            reasoning = msg.get("reasoning")
            if isinstance(reasoning, str) and reasoning.strip():
                await emit_thinking(reasoning)
        if round_thinking:
            thinking_parts.append("".join(round_thinking))

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            content = msg.get("content")
            text = str(content or "").strip()
            if (
                drift_retry
                and not tool_used
                and text
                and len(text) < _DRIFT_MAX_CHARS
                and not drift_corrected
                and round_i < max_rounds - 1
            ):
                drift_corrected = True
                # The rejected narration never entered working, so quote it inside the
                # hint itself — the model cannot see a message that is not there.
                transient = [{
                    "role": "system",
                    "content": (
                        _DRIFT_HINT["content"]
                        + f'\nFor reference, your unacted announcement was: "{text[:200]}"'
                    ),
                }]
                logger.info(
                    "Agent detects toolless action narration (round=%s, %s characters), injects correction prompts and tries again",
                    round_i,
                    len(text),
                )
                continue
            if content:
                return LoopResult(
                    messages=working,
                    final_content=str(content),
                    tool_used=tool_used,
                    thinking=_join_thinking(thinking_parts),
                )
            break

        tool_used = True
        limited = tool_calls[:max_tools_per_round]
        dropped = tool_calls[max_tools_per_round:]
        # Declare every requested call so truncated ones stay protocol-paired;
        # their synthetic observations below tell the model what happened.
        working.append({
            "role": "assistant",
            "content": msg.get("content"),
            "tool_calls": tool_calls,
        })

        async def _run_one(tc: dict[str, Any]) -> tuple[str, bool]:
            fn = tc.get("function") or {}
            name = str(fn.get("name") or "")
            args = parse_tool_arguments(fn.get("arguments"))
            try:
                result = await execute(name, args)
                if compact_observation is not None:
                    result = await compact_observation(str(result or ""))
                else:
                    result = _truncate_tool_result(str(result or ""))
                return result, False
            except AgentHalt as halt:
                observation = halt.observation
                if compact_observation is not None:
                    observation = await compact_observation(observation)
                else:
                    observation = _truncate_tool_result(observation)
                return observation, True
            except ApiBusinessError:
                raise
            except Exception as tool_exc:
                logger.warning("Tool execution failed tool=%s: %s", name, tool_exc)
                # Domain guards that persist their own failure record mark the
                # exception with ``already_logged`` and classify it via
                # ``error_kind`` (see ToolGuardError in the interview domain).
                # The attributes are a duck-typed contract: absent ones fall
                # back to a plain tool failure, exactly one record per failure.
                if not getattr(tool_exc, "already_logged", False):
                    domain, session = error_scope(error_context)
                    log_agent_error(
                        domain=domain, session=session, tool=name,
                        kind=getattr(tool_exc, "error_kind", "tool_failed"),
                        message=str(tool_exc),
                    )
                return f"Tool execution failed: {tool_exc}", False

        outcomes = await asyncio.gather(*(_run_one(tc) for tc in limited))
        halted = False
        # Position suffix keeps fallback ids collision-free even when the model
        # emitted several id-less calls of the same name in one round.
        for position, (tc, (result, did_halt)) in enumerate(zip(limited, outcomes)):
            fn = tc.get("function") or {}
            name = str(fn.get("name") or "")
            args = parse_tool_arguments(fn.get("arguments"))
            tc_id = str(tc.get("id") or f"call_{round_i}_{name}_{position}")
            working.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": result,
            })
            if on_tool is not None:
                maybe = on_tool(name, args, result, tc_id)
                if maybe is not None and inspect.isawaitable(maybe):
                    await maybe
            halted = halted or did_halt
        # Position suffix keeps synthetic ids collision-free even when the
        # model emitted several id-less calls of the same name this round.
        for position, tc in enumerate(dropped):
            fn = tc.get("function") or {}
            name = str(fn.get("name") or "")
            tc_id = str(tc.get("id") or f"call_{round_i}_{name}_budget_{position}")
            working.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": (
                    f"[{name}] Not executed: the per-round tool budget "
                    f"({max_tools_per_round}) was exhausted. Re-issue this call "
                    "next round if it is still needed."
                ),
            })
        if halted:
            break

    return LoopResult(
        messages=working,
        final_content=None,
        tool_used=tool_used,
        halted=halted,
        thinking=_join_thinking(thinking_parts),
    )
