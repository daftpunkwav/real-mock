"""Clean XML tool-call blocks inlined in text (function-calling protocol drift).

The model occasionally emits ``<tool_call><invoke name="quiz">…</invoke></tool_call>`` in the body
instead of using the tools channel. Such blocks are pure noise to the user: remove the entire block; the quiz
``<question>`` is valid content, so convert it to question text and let it through, avoiding a promise to ask a question with no question shown.
Streaming-safe: once a block begins, buffer through its closing tag (or end of stream) before processing it; pass through an oversized unclosed block as body text.

The block rendering strategy is injected through the :class:`InlineToolCallCleaner` constructor argument ``quiz_renderer``.
The default renderer is deliberately neutral (question text passes through unchanged): business-specific
copy belongs to the calling domain, which supplies its own renderer.
"""

from __future__ import annotations

import re
from collections.abc import Callable

# Extraction of text inline XML tool call blocks (for quiz question conversion)
_INLINE_QUESTION_RE = re.compile(r"<question>(.*?)</question>", re.S)

QuizBlockRenderer = Callable[[str], str]


def _default_quiz_renderer(question: str) -> str:
    """Neutral fallback: keep the extracted question text; drop empty blocks."""
    if not question:
        return ""
    return question


class InlineToolCallCleaner:
    """Handle XML tool-call blocks inlined in the text channel (function-calling protocol drift).

    The model occasionally emits ``<tool_call><invoke name="quiz">…</tool_call>`` in the body
    instead of using the tools channel. Such blocks are pure noise to the user: remove the entire block; the quiz
    ``<question>`` is valid content, so convert it to question text and let it through, avoiding a promise to ask a question with no question shown.
    Streaming-safe: once a block begins, buffer through its closing tag (or end of stream) before processing it; pass through an oversized unclosed block as body text.
    """

    _OPEN = "<tool_call>"
    _CLOSE = "</tool_call>"
    _MAX_BLOCK = 4000
    # <tool_call> (blank allowed) must be followed by <invoke before it is recognized as a tool block;
    # Legal discussion in the text <tool_call> (such as teaching example) does not contain invoke, and is released according to the text
    _INVOKE_WINDOW = 64

    def __init__(self, *, quiz_renderer: QuizBlockRenderer | None = None) -> None:
        self._buf = ""
        self._in_block = False
        self._quiz_renderer: QuizBlockRenderer = quiz_renderer or _default_quiz_renderer

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self._buf += chunk
        return self._drain(final=False)

    def flush(self) -> str:
        return self._drain(final=True)

    def _convert_block(self, block: str) -> str:
        m = _INLINE_QUESTION_RE.search(block)
        question = m.group(1).strip() if m else ""
        return self._quiz_renderer(question)

    def _drain(self, final: bool) -> str:
        out: list[str] = []
        while True:
            if not self._in_block:
                i = self._buf.find(self._OPEN)
                if i < 0:
                    if final:
                        self._emit_local(out, self._buf)
                        self._buf = ""
                        break
                    keep = 0
                    for k in range(min(len(self._OPEN) - 1, len(self._buf)), 0, -1):
                        if self._buf.endswith(self._OPEN[:k]):
                            keep = k
                            break
                    emit_len = len(self._buf) - keep
                    if emit_len > 0:
                        self._emit_local(out, self._buf[:emit_len])
                        self._buf = self._buf[emit_len:]
                    break
                rest_start = i + len(self._OPEN)
                window = self._buf[rest_start : rest_start + self._INVOKE_WINDOW]
                stripped = window.lstrip()
                if not stripped:
                    if not final and len(window) < self._INVOKE_WINDOW:
                        break  # The back is still blank, waiting for more data to be confirmed.
                    # The window is completely blank: it is not a tool block, and the word <tool_call> is allowed.
                    self._emit_local(out, self._buf[:rest_start])
                    self._buf = self._buf[rest_start:]
                    continue
                if not stripped.startswith("<invoke"):
                    # Non-blank content is not <invoke: it is a text discussion, release <tool_call>
                    self._emit_local(out, self._buf[:rest_start])
                    self._buf = self._buf[rest_start:]
                    continue
                if i > 0:
                    self._emit_local(out, self._buf[:i])
                self._buf = self._buf[rest_start:]
                self._in_block = True
                continue
            # Within block: find closure
            j = self._buf.find(self._CLOSE)
            if j < 0:
                if final:
                    self._emit_local(out, self._convert_block(self._buf))
                    self._buf = ""
                    self._in_block = False
                    break
                if len(self._buf) > self._MAX_BLOCK:
                    # Extra long unclosed text: regarded as the main text and allowed to pass, to avoid swallowing the normal content.
                    self._emit_local(out, self._buf)
                    self._buf = ""
                    self._in_block = False
                break
            self._emit_local(out, self._convert_block(self._buf[:j]))
            self._buf = self._buf[j + len(self._CLOSE):]
            self._in_block = False
        return "".join(out)

    @staticmethod
    def _emit_local(out: list[str], text: str) -> None:
        if text:
            out.append(text)
