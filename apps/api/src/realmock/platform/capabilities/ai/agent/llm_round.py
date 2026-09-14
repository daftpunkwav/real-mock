"""Single-turn LLM call: prefer streaming, fall back to non-streaming, and truncate tool results.

Decoupled from the main orchestration in ``loop.run_agent_loop``: single-turn calls/fallback logic and tool-result truncation rules
are centralized here; loop advancement and message pairing remain in ``loop.py``.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from realmock.platform.capabilities.ai.llm.defaults import TOOL_OBSERVATION_SOFT_CHARS

logger = logging.getLogger(__name__)

# Loop callback contract: execute runs domain tools; on_tool / on_thinking are event callbacks
ExecuteFn = Callable[[str, dict[str, Any]], Awaitable[str]]
OnToolFn = Callable[[str, dict[str, Any], str, str], Awaitable[None] | None]
OnThinkFn = Callable[[str], Awaitable[None] | None]
#: One-argument text-delta callback (reasoning or raw body text); may be sync or async.
OnTextFn = Callable[[str], Awaitable[None] | None]

# Soft cap used when a domain does not supply LLM compression.
MAX_TOOL_RESULT_CHARS = TOOL_OBSERVATION_SOFT_CHARS


def _truncate_tool_result(text: str, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n…[truncated]"


async def _call_llm_round(
    llm: Any,
    call_messages: list[dict[str, Any]],
    *,
    temperature: float,
    tools: list[dict[str, Any]] | None,
    emit_thinking: OnThinkFn,
    emit_content: OnTextFn | None = None,
) -> dict[str, Any]:
    """One model call: prefer streaming (with real-time reasoning-delta callbacks), falling back to
non-streaming when unsupported.

    On the streaming path, response text/tool calls are assembled by the client into a message
    event matching the non-streaming ``chat_message`` shape; reasoning deltas have already been
    delivered in real time, so the ``reasoning`` key is not read again.
    ``emit_content``: optional real-time callback for raw body-text deltas (speculative
    streaming — the caller decides whether the round's text is a final answer only after
    the round completes); absent on the non-streaming fallback.
    """
    streamer = getattr(llm, "chat_message_stream", None)
    if streamer is None:
        return await llm.chat_message(call_messages, temperature=temperature, tools=tools)
    try:
        msg: dict[str, Any] | None = None
        async for event in streamer(call_messages, temperature=temperature, tools=tools):
            etype = event.get("type")
            if etype == "reasoning":
                await emit_thinking(str(event.get("text") or ""))
            elif etype == "text" and emit_content is not None:
                maybe = emit_content(str(event.get("text") or ""))
                if maybe is not None and inspect.isawaitable(maybe):
                    await maybe
            elif etype == "message":
                candidate = event.get("message")
                if isinstance(candidate, dict):
                    msg = candidate
        if msg is not None:
            return msg
        logger.warning("The Agent's streaming round did not return a message and fell back to non-streaming.")
    except NotImplementedError:
        logger.info("LLM does not support the streaming tool wheel and falls back to non-streaming: %s", type(llm).__name__)
    return await llm.chat_message(call_messages, temperature=temperature, tools=tools)
