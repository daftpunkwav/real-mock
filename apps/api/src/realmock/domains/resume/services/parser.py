"""AI-powered resume transcription and structured parsing.

Responsibilities:
- Transcribe image-only PDF pages via vision
- Parse extracted text into ``CandidateProfile`` via LLM (degrade to summary)

Plain-text extraction lives in ``text_extract``; page rendering for
image-only PDFs lives in ``render``. Limits live in ``schemas.limits``.
Must not import FastAPI or ORM.
"""

from __future__ import annotations

import asyncio
import logging

from realmock.domains.resume.prompts import (
    PARSE_SYSTEM_PROMPT,
    TRANSCRIBE_SYSTEM_PROMPT,
)
from realmock.domains.resume.services.text_extract import truncate_text
from realmock.platform.schemas import CandidateProfile
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.domains.resume.schemas.limits import (
    PARSE_FALLBACK_SUMMARY_CHARS,
    PARSE_LLM_CHARS,
    TRANSCRIBE_CONCURRENCY,
)
from realmock.platform.capabilities.ai.context.blobs import compress_text_blob

logger = logging.getLogger(__name__)

async def transcribe_pages_with_vision(
    page_images: list[str],
    llm: LLMClient,
) -> str:
    """Use the visual model to convert image-based PDF pages into plain text.

    Pages are transcribed concurrently (``TRANSCRIBE_CONCURRENCY`` cap) so a
    multi-page scan takes roughly one page's latency instead of the sum; page
    order is preserved in the joined output. One page failure fails the whole
    transcription — a partial resume text would silently truncate content.
    """
    if not page_images:
        return ""

    sem = asyncio.Semaphore(TRANSCRIBE_CONCURRENCY)

    async def one(idx: int, image: str) -> str:
        content = [
            {"type": "text", "text": "Please transcribe this resume page verbatim."},
            {"type": "image_url", "image_url": {"url": image}},
        ]
        async with sem:
            text = await llm.chat(
                [
                    {"role": "system", "content": TRANSCRIBE_SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
                temperature=0.2,
            )
        return f"<!-- page {idx + 1} -->\n{text.strip()}"

    pages = await asyncio.gather(
        *(one(i, url) for i, url in enumerate(page_images))
    )
    return truncate_text("\n\n".join(pages))


async def parse_resume_with_llm(
    raw_text: str,
    llm: LLMClient,
) -> CandidateProfile:
    """Use LLM to parse resume text into a Candidate Profile."""
    source = raw_text or ""
    if len(source) > PARSE_LLM_CHARS:
        source = await compress_text_blob(
            llm,
            source,
            soft_chars=PARSE_LLM_CHARS,
            target_chars=PARSE_LLM_CHARS,
            purpose="resume parse input",
        )
    messages = [
        {"role": "system", "content": PARSE_SYSTEM_PROMPT},
        {"role": "user", "content": f"Please parse the following resume:\n\n{source}"},
    ]
    try:
        data = await llm.chat_json(messages)
        blob = dict(data) if isinstance(data, dict) else {}
        blob.pop("parse_degraded", None)
        profile = CandidateProfile(**blob)
        return profile.model_copy(update={"parse_degraded": False})
    except Exception as e:
        logger.warning("LLM resume parsing failed, use basic parsing: %s", e)
        return CandidateProfile(
            summary=raw_text[:PARSE_FALLBACK_SUMMARY_CHARS],
            parse_degraded=True,
        )
