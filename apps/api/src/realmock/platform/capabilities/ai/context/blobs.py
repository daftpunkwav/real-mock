"""LLM compression for oversized text blobs.

Agents must not hard-slice evidence. When a blob exceeds the soft cap, ask the
LLM to compress it. If that call fails, return a head+tail excerpt that is
explicitly marked as a compression failure — never a silent mid-string cut.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from realmock.platform.capabilities.ai.llm.defaults import (
    COMPACTION_SUMMARY_MAX_TOKENS,
    COMPRESSION_TIMEOUT_SECONDS,
    TOOL_OBSERVATION_COMPRESSED_CHARS,
    TOOL_OBSERVATION_SOFT_CHARS,
)

logger = logging.getLogger(__name__)

_COMPRESS_PROMPT = (
    "Compress the following tool observation for a later model turn. "
    "Keep facts, numbers, URLs, file paths, verdicts, and contradictions. "
    "Drop repetition and boilerplate. Do not invent content. Output plain text only."
)


def _head_tail(text: str, budget: int, *, marker: str) -> str:
    if len(text) <= budget:
        return text
    keep = max(80, (budget - 80) // 2)
    return (
        text[:keep]
        + f"\n…[{marker}: middle omitted; original "
        + str(len(text))
        + " chars]…\n"
        + text[-keep:]
    )


async def compress_text_blob(
    llm: Any | None,
    text: str,
    *,
    soft_chars: int = TOOL_OBSERVATION_SOFT_CHARS,
    target_chars: int = TOOL_OBSERVATION_COMPRESSED_CHARS,
    purpose: str = "tool observation",
) -> str:
    """Compress ``text`` when it exceeds ``soft_chars``.

    ``llm=None`` skips the model and uses the marked head+tail excerpt so the
    caller still receives an explicit failure marker.
    """
    blob = text or ""
    if len(blob) <= soft_chars:
        return blob
    if llm is None or not getattr(llm, "chat", None):
        logger.warning("Blob compression skipped (no LLM) purpose=%s chars=%s", purpose, len(blob))
        return _head_tail(blob, target_chars, marker="NO_LLM_EXCERPT")
    try:
        summary = await asyncio.wait_for(
            llm.chat(
                [
                    {"role": "system", "content": _COMPRESS_PROMPT},
                    {
                        "role": "user",
                        "content": f"Purpose: {purpose}\n\n{blob}",
                    },
                ],
                temperature=0.1,
                max_tokens=COMPACTION_SUMMARY_MAX_TOKENS,
            ),
            timeout=COMPRESSION_TIMEOUT_SECONDS,
        )
        compact = str(summary or "").strip()
        if compact and len(compact) <= target_chars:
            prefix = f"[compressed from {len(blob)} chars]\n"
            return prefix + compact
        if compact:
            logger.warning(
                "Blob compression still too long purpose=%s chars=%s compact=%s",
                purpose,
                len(blob),
                len(compact),
            )
        else:
            logger.warning("Blob compression returned empty purpose=%s chars=%s", purpose, len(blob))
    except Exception as exc:
        logger.warning("Blob compression failed purpose=%s: %s", purpose, exc)
    return _head_tail(blob, target_chars, marker="COMPRESSION_FAILED")


__all__ = ["compress_text_blob"]
