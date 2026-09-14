"""LLM streaming-output sanitizer (public entry point).

Solves three observed leak classes:

- Models emit training-template special tokens (such as ``<|minimax|>``) as body text, and forwarding each token
  unchanged displays them directly in the user's message bubble; strip them safely across stream chunks here.
- Models occasionally degrade function calling to inline XML in the text body (``<tool_call>…</tool_call>``),
  which is pure noise to users; the quiz ``<question>`` remains valid content and is converted to question text.
- Reasoning deltas (OpenAI ``reasoning_content`` / Anthropic ``thinking_delta``)
  must be wrapped consistently in ``<think>...</think>`` to match the frontend ``splitThinkAnswer`` contract.

All LLM clients (openai_chat / anthropic_messages / responses) share this module,
ensuring consistent user-visible text across all three protocols.

Implementation layers:
- ``special_token_filter.py``: streaming removal of ``<|X|>`` / ``<]X[>``;
- ``inline_tool_call.py``: clean inline ``<tool_call>`` XML blocks (quiz → body text);
- ``stream_sanitizer.py``: dual-channel orchestration;
- This file: public-symbol re-exports + one-shot ``sanitize_special_tokens``.
"""

from __future__ import annotations

from .inline_tool_call import InlineToolCallCleaner
from .special_token_filter import SpecialTokenFilter, _SPECIAL_RE
from .stream_sanitizer import StreamSanitizer

__all__ = [
    "InlineToolCallCleaner",
    "SpecialTokenFilter",
    "StreamSanitizer",
    "sanitize_special_tokens",
]


def sanitize_special_tokens(text: str) -> str:
    """One-time purification of non-streaming text (used for the entire text)."""
    if not text:
        return text
    cleaner = InlineToolCallCleaner()
    return cleaner.feed(_SPECIAL_RE.sub("", text)) + cleaner.flush()
