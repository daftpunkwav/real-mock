"""Prep streaming helpers: speculative content tokens, event queue for tool rounds, and early-body replay.

The orchestration layer (``chat_stream`` in :mod:`agent`) uses :func:`stream_tool_rounds`
to run tool rounds in the background and relay their event queue; :func:`event_loopbacks`
builds the per-round callbacks (thinking deltas, tool progress, and display-filtered
speculative content tokens); :func:`slice_stream` replays a fully buffered answer body
in small slices.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from realmock.platform.capabilities.ai.llm.stream_filters import (
    InlineToolCallCleaner,
    SpecialTokenFilter,
)

logger = logging.getLogger(__name__)

# Early content slice playback: simulate segment-by-segment output to avoid instantaneous display of the entire segment
_EARLY_SLICE_CHARS = 48
_EARLY_SLICE_DELAY = 0.02

# Tool-step detail budgets for display/persistence. The model-side observation is
# compressed separately by compact_observation (soft 12k -> LLM 4k); these caps only
# bound what travels over SSE and into the steps metadata (safety valve, stated).
_STEP_ARG_VALUE_CHARS = 500
_STEP_RESULT_CHARS = 20_000
_STEP_TRUNCATION_MARKER = "…[display truncated: {total} chars total]…"

# produce coroutine end sentry (used for event queue of chat_stream)
_PRODUCE_DONE = object()

# Cap for one held-back inline tool-call block in the display filter; beyond it
# the block is released as body text (same tolerance as the platform cleaner).
_DISPLAY_BLOCK_MAX_CHARS = 4000


class DisplayTextFilter:
    """Incremental display mirror of the persist-path sanitization (``polish_final``).

    Speculative streaming shows model body text before the loop knows whether a
    round is final, so the display channel must apply the same rules the final
    answer will get, or refresh would rewrite what the user just read:

    - ``<tool_call>…</tool_call>`` blocks mentioning ``ask_user`` are held back
      and dropped — the JSON-style drift form ``polish_final`` strips at persist
      (the platform cleaner releases invoke-less blocks as text, so this filter
      owns that rule);
    - template special tokens and ``<invoke>``-style tool blocks are removed via
      the platform filters (quiz ``<question>`` converts to body text);
    - emojis are NOT removed — ``polish_final`` keeps them, so display and
      persisted history must keep them too;
    - leading whitespace of the first emission is stripped (mirrors
      ``polish_final``'s final ``strip()``); trailing whitespace is not
      retracted live — polish strips it at persist and HTML renders it away.

    Output is display-only: the persisted message always comes from
    ``polish_final`` on the raw final text (which also rescues buildable
    ask_user blocks into dialog events).
    """

    _OPEN = "<tool_call>"
    _CLOSE = "</tool_call>"

    def __init__(self) -> None:
        self._buf = ""
        self._in_block = False
        self._emitted = False
        self._tokens = SpecialTokenFilter()
        self._tool_calls = InlineToolCallCleaner()

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self._buf += chunk
        out: list[str] = []
        while True:
            if not self._in_block:
                i = self._buf.find(self._OPEN)
                if i < 0:
                    # Hold back a trailing partial opening so a split
                    # "<tool_c…all>" never flashes before its block is dropped.
                    keep = 0
                    for k in range(min(len(self._OPEN) - 1, len(self._buf)), 0, -1):
                        if self._buf.endswith(self._OPEN[:k]):
                            keep = k
                            break
                    emit_len = len(self._buf) - keep
                    if emit_len > 0:
                        out.append(self._buf[:emit_len])
                        self._buf = self._buf[emit_len:]
                    break
                out.append(self._buf[:i])
                self._buf = self._buf[i + len(self._OPEN):]
                self._in_block = True
                continue
            j = self._buf.find(self._CLOSE)
            if j < 0:
                if len(self._buf) > _DISPLAY_BLOCK_MAX_CHARS:
                    # Unclosed oversized block: release as body text (polish
                    # would keep it too — its regex needs the closing tag).
                    out.append(self._buf)
                    self._buf = ""
                    self._in_block = False
                break
            block = self._buf[:j]
            self._buf = self._buf[j + len(self._CLOSE):]
            self._in_block = False
            if "ask_user" not in block:
                out.append(self._OPEN + block + self._CLOSE)
            # ask_user blocks are dropped: the dialog event (when the args are
            # buildable) is produced by polish_final on the raw final text.
        return self._emit_downstream("".join(out))

    def flush(self) -> str:
        # An unclosed held block releases as text; downstream filters flush too.
        tail, self._buf, self._in_block = self._buf, "", False
        return self._emit_downstream(tail)

    def _emit_downstream(self, text: str) -> str:
        """Run released text through the platform filters, mirroring polish_final's
        leading strip on the first emission (trailing whitespace cannot be
        retracted live; polish strips it at persist and HTML renders it away)."""
        result = self._tool_calls.feed(self._tokens.feed(text))
        if result and not self._emitted:
            result = result.lstrip()
        if result:
            self._emitted = True
        return result


def make_display_filter() -> DisplayTextFilter:
    """Factory for the per-turn display filter (owned by the chat orchestration)."""
    return DisplayTextFilter()


def event_loopbacks(
    events: asyncio.Queue | None,
    on_tool_step: Any | None = None,
    content_state: dict[str, Any] | None = None,
) -> tuple[Any, Any, Any]:
    """Build event callbacks for the tool loop: send reasoning deltas, tool progress, and
    speculative content tokens to the frontend immediately.

    ``on_tool_step`` is optional: when tool progress arrives, record it synchronously (for example,
    in a ``tool_steps`` list for persistence). ``content_state`` enables speculative streaming:
    raw body-text deltas from every round pass through the caller-owned ``filter``
    (:class:`DisplayTextFilter`, the display mirror of ``polish_final``) and are relayed as
    ``token`` events; the first delta also clears the status line. The caller owns the dict
    (``streamed`` / ``status_cleared`` / ``raw`` plus the ``filter``) so it can flush the
    held-back tail after the loop returns. Returns ``(on_thinking, on_tool, on_content)``;
    when ``events`` is None, the callbacks are no-ops (the non-streaming channel need not
    emit events).
    """
    async def on_thinking(text: str) -> None:
        # Model thinking increment (streaming rounds segment by segment / non-streaming entire segment): events are delivered to the front end in real time
        if events is not None:
            await events.put({"type": "thinking", "content": text})

    async def on_tool(name: str, args: dict[str, Any], result: str, tc_id: str) -> None:
        safe_args = args if isinstance(args, dict) else {}
        query = (
            safe_args.get("query")
            or safe_args.get("company")
            or safe_args.get("repo")
            or safe_args.get("question")
            or safe_args.get("content")
            or ""
        )
        step = {
            "name": name,
            "query": str(query)[:120],
            "args": _public_args(args),
            "result": _display_result(result),
        }
        if on_tool_step is not None:
            on_tool_step(step)
        if events is not None:
            await events.put({"type": "tool_step", **step})

    async def on_content(text: str) -> None:
        if events is None or content_state is None or not text:
            return
        if not content_state.get("status_cleared"):
            content_state["status_cleared"] = True
            await events.put({"type": "status", "text": ""})
        cleaned = content_state["filter"].feed(text)
        if cleaned:
            content_state["streamed"] = True
            content_state["raw"] = str(content_state.get("raw") or "") + cleaned
            await events.put({"type": "token", "content": cleaned})

    return on_thinking, on_tool, on_content


def _public_args(args: dict[str, Any]) -> dict[str, str]:
    """Argument detail for display: stringified values, each capped (no secrets in prep args)."""
    public: dict[str, str] = {}
    if not isinstance(args, dict):
        return public
    # No sorted(): keys are virtually always strings, but a non-string key
    # must never raise here and wipe the turn's tool progress upstream.
    for key, value in args.items():
        name = str(key)
        if name.startswith("_"):
            continue
        public[name] = str(value or "")[:_STEP_ARG_VALUE_CHARS]
    return public


def _display_result(result: Any) -> str:
    """Observation text for display: the exact text the model saw (possibly LLM-compressed).

    Capped only as a safety valve with an explicit marker; the model-side
    compression already happened upstream via compact_observation.
    """
    text = str(result or "")
    if len(text) <= _STEP_RESULT_CHARS:
        return text
    return text[:_STEP_RESULT_CHARS] + _STEP_TRUNCATION_MARKER.format(total=len(text))


def slice_stream(text: str) -> AsyncIterator[str]:
    """Play back the topic content obtained at one time in small pieces to ensure smooth display on the front end."""
    async def _gen() -> AsyncIterator[str]:
        for k in range(0, len(text), _EARLY_SLICE_CHARS):
            yield text[k : k + _EARLY_SLICE_CHARS]
            if k + _EARLY_SLICE_CHARS < len(text):
                await asyncio.sleep(_EARLY_SLICE_DELAY)
    return _gen()


async def stream_tool_rounds(
    run: Any,
    outcome: dict[str, Any],
    events: asyncio.Queue,
    *args: Any,
    **kwargs: Any,
) -> AsyncIterator[Any]:
    """Run one tool loop in the background and relay its event queue until the ``_PRODUCE_DONE`` sentinel.

    Inject ``events=events`` into ``run`` (tool progress/reasoning/dialog events enter the queue
    in real time); write the return value to ``outcome["value"]`` (or an exception to
    ``outcome["error"]``) for the caller to consume after the stream ends. As before, a tool-round
    failure does not interrupt streaming. Cancellation is awaited so no orphan
    task (and no unretrieved exception) survives the stream.
    """
    async def produce() -> None:
        try:
            outcome["value"] = await run(*args, events=events, **kwargs)
        except Exception as e:
            logger.warning("Prep tool wheel exception: %s", e)
            outcome["error"] = e
        await events.put(_PRODUCE_DONE)

    task = asyncio.create_task(produce())
    try:
        while True:
            item = await events.get()
            if item is _PRODUCE_DONE:
                break
            yield item
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                # The exception is already recorded in outcome["error"]; log once
                # so a cancelled stream never emits "exception was never retrieved".
                logger.warning("Prep tool-round background task ended: %s", e)


__all__ = [
    "_PRODUCE_DONE",
    "event_loopbacks",
    "slice_stream",
    "stream_tool_rounds",
]
