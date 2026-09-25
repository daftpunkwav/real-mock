"""JSON extraction and grounded repair for report-agent output.

Adapted from the resume-review finalizer (balanced-brace scan keeps the
key-richest candidate object; a bounded LLM repair pass grounded in gathered
evidence is the last resort before failure).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from realmock.domains.records.agents.report.prompts import report_repair_system
from realmock.platform.capabilities.ai.context.blobs import compress_text_blob
from realmock.platform.capabilities.ai.llm.json_extract import (
    extract_json_object,
    truncate_chunk,
)

logger = logging.getLogger(__name__)

_REPAIR_TIMEOUT_SECONDS = 120.0

# Per-chunk budgets preserved from the original implementation; truncation is
# now head+tail with an explicit marker instead of a silent slice.
_TOOL_EVIDENCE_CHARS = 4_000
_DRAFT_EVIDENCE_CHARS = 8_000
_FALLBACK_EVIDENCE_CHARS = 12_000


def _evidence_text(messages: list[dict[str, Any]], draft: str) -> str:
    """Flatten tool observations and the draft into repair evidence."""
    chunks: list[str] = []
    for message in messages:
        if str(message.get("role") or "") == "tool":
            text = str(message.get("content") or "").strip()
            if text:
                name = str(message.get("name") or message.get("tool_call_id") or "tool")
                chunks.append(
                    f"TOOL_{name}:\n{truncate_chunk(text, limit=_TOOL_EVIDENCE_CHARS)}"
                )
    draft_text = (draft or "").strip()
    if draft_text:
        chunks.append("DRAFT:\n" + truncate_chunk(draft_text, limit=_DRAFT_EVIDENCE_CHARS))
    return "\n\n".join(chunks)


async def repair_json(
    llm: Any,
    messages: list[dict[str, Any]],
    draft: str,
    *,
    schema_text: str,
    purpose: str,
) -> dict[str, Any] | None:
    """Grounded repair pass; returns the repaired object or None."""
    evidence = _evidence_text(messages, draft)
    if not evidence.strip():
        return None
    try:
        compressed = await compress_text_blob(llm, evidence, purpose=purpose)
    except Exception:
        compressed = truncate_chunk(evidence, limit=_FALLBACK_EVIDENCE_CHARS)
    try:
        repaired = await asyncio.wait_for(
            llm.chat_json(
                [
                    {
                        "role": "system",
                        "content": report_repair_system(schema_text),
                    },
                    {"role": "user", "content": compressed},
                ],
                temperature=0.2,
            ),
            timeout=_REPAIR_TIMEOUT_SECONDS,
        )
        return repaired if isinstance(repaired, dict) else None
    except Exception as e:
        logger.warning("report JSON repair failed (%s): %s", purpose, e)
        return None


async def finalize_json(
    llm: Any,
    loop_result: Any,
    *,
    schema_text: str,
    purpose: str,
) -> dict[str, Any] | None:
    """Parse a ReAct loop's final content; repair from evidence when not JSON."""
    payload = extract_json_object(loop_result.final_content or "")
    if payload is not None:
        return payload
    logger.info(
        "%s final content was not JSON (len=%s); running grounded repair",
        purpose,
        len(str(loop_result.final_content or "")),
    )
    return await repair_json(
        llm,
        loop_result.messages,
        loop_result.final_content or "",
        schema_text=schema_text,
        purpose=purpose,
    )


__all__ = ["extract_json_object", "finalize_json", "repair_json"]
