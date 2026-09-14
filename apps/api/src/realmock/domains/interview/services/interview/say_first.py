"""say-first protocol parsing: non-streaming parsing of early tool-round text + streaming incremental parsing.

Extracted from :mod:`realmock.domains.interview.services.interview.runner` and shared by all three
streaming entry points. think stripping comes first and protocol parsing second, with the two layers
independent; on fallback (output does not follow the protocol), ``TurnOutput.say`` contains all visible
text and control fields use their defaults.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from realmock.domains.interview.services.interview.agent_text import (
    ThinkStreamFilter,
    strip_think_blocks,
)
from realmock.domains.interview.services.interview.events import StreamEvent
from realmock.domains.interview.services.interview.turn_output import TurnOutput, parse_turn_output
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.capabilities.ai.llm.say_first_stream import SayFirstStreamParser


def parse_complete_output(text: str) -> TurnOutput:
    """Say-first parsing and fallback for early text on non-streaming tool turns.

    When the model returns a direct text answer during a tool turn, the body follows the say-first protocol as well;
    if parsing the whole response fails, treat the original text as say (matching the streaming fallback semantics).
    """
    visible = strip_think_blocks(text or "")
    try:
        parsed = json.loads(visible.strip())
    except Exception:
        return parse_turn_output(None, say_text=visible, degraded=True)
    if isinstance(parsed, dict) and isinstance(parsed.get("say"), str):
        return parse_turn_output(parsed, say_text=parsed["say"])
    return parse_turn_output(None, say_text=visible, degraded=True)


async def stream_say_first(
    llm: LLMClient,
    tools: Any,
    api_messages: list[dict[str, Any]],
    *,
    temperature: float,
) -> AsyncIterator[StreamEvent | TurnOutput]:
    """Stream an LLM call and parse it according to the say-first protocol.

    ``tools`` must expose ``collect_chat_tools`` (that is, :class:`ToolRoundRunner`).
    Yield TOKEN events (plaintext say deltas), then yield TurnOutput for caller cleanup.
    """
    think_filter = ThinkStreamFilter()
    parser = SayFirstStreamParser()
    say_parts: list[str] = []
    stream_tools = tools.collect_chat_tools(include_function_tools=False)
    async for token in llm.chat_stream(
        api_messages, temperature=temperature, tools=stream_tools
    ):
        visible = think_filter.feed(token or "")
        if not visible:
            continue
        say_chunk = parser.feed(visible)
        if say_chunk:
            say_parts.append(say_chunk)
            yield StreamEvent.make_token(say_chunk)
    tail = parser.finish()
    if tail:
        say_parts.append(tail)
        yield StreamEvent.make_token(tail)
    say_text = parser.raw_text if parser.degraded else "".join(say_parts)
    yield parse_turn_output(
        parser.controls,
        say_text=say_text,
        degraded=parser.degraded,
    )


__all__ = ["parse_complete_output", "stream_say_first"]
