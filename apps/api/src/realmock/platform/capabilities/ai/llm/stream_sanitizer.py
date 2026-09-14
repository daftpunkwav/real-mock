"""Orchestration for dual-channel streaming sanitization of reasoning/content.

Combines special-token stripping with inline tool-call cleanup:
- ``feed_reasoning``: prepend ``<think>`` on the first call, then emit the content after removing emoji;
- ``feed_content``: if ``<think>`` is still open, first append ``</think>``, then emit the content
  after removing emoji and stripping special tokens;
- ``flush``: finalize the stream (close any open tag + release buffered content).
"""

from __future__ import annotations

from realmock.platform.core.prompts import strip_emojis

from .inline_tool_call import InlineToolCallCleaner
from .special_token_filter import SpecialTokenFilter


class StreamSanitizer:
    """Dual-channel streaming sanitization for reasoning/content.

    - ``feed_reasoning``: prepend ``<think>`` on the first call, then emit the content after removing emoji;
    - ``feed_content``: if ``<think>`` is still open, first append ``</think>``, then emit the content
      after removing emoji and stripping special tokens;
    - ``flush``: finalize the stream (close any open tag + release buffered content).
    """

    def __init__(self) -> None:
        self._tokens = SpecialTokenFilter()
        self._tool_calls = InlineToolCallCleaner()
        self._reasoning_open = False

    def feed_reasoning(self, chunk: str) -> str:
        out: list[str] = []
        if not self._reasoning_open:
            out.append("<think>")
            self._reasoning_open = True
        out.append(strip_emojis(chunk))
        return "".join(out)

    def feed_content(self, chunk: str) -> str:
        out: list[str] = []
        if self._reasoning_open:
            out.append("</think>")
            self._reasoning_open = False
        cleaned = self._tokens.feed(strip_emojis(chunk))
        out.append(self._tool_calls.feed(cleaned))
        return "".join(out)

    def flush(self) -> str:
        out: list[str] = []
        if self._reasoning_open:
            out.append("</think>")
            self._reasoning_open = False
        out.append(self._tool_calls.feed(self._tokens.flush()))
        out.append(self._tool_calls.flush())
        return "".join(out)
