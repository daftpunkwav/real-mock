"""
@file quiz_render.py
@description Prep-domain rendering of inline quiz tool-call drift.

When the model emits ``<tool_call><invoke name="quiz">...<question>..</question>``
inline in the body channel, the platform cleaner strips the XML and passes the
extracted question through this renderer so the user sees a coaching-style
prompt instead of raw markup or silence.
"""

from __future__ import annotations

# Product copy for prep-domain inline quiz drift (rendered after the XML block
# is removed). Kept in the prep domain so the platform cleaner stays neutral.
_PREP_QUIZ_BLOCK_TEMPLATE = (
    "**Practice questions**: {question}\n\n"
    "Please answer directly and I will comment on them sentence by sentence."
)


def prep_quiz_renderer(question: str) -> str:
    """Render an inline quiz question as coaching body text.

    Empty questions are dropped entirely (the block is noise with no usable
    content). The result is later sanitized for special tokens before display.
    """
    if not question:
        return ""
    return _PREP_QUIZ_BLOCK_TEMPLATE.format(question=question)


__all__ = ["prep_quiz_renderer"]
