"""Resume-text extraction orchestration.

Responsibilities:
- Extract text; fall back to vision transcription for image-only PDFs
- Translate extraction failures into A1004 / A1006

On-disk lookup lives in ``files``. Atomic parse/render live in ``parser`` /
``render``. Must not import FastAPI routers.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from realmock.domains.resume.services.files import find_resume_file, find_resume_files
from realmock.domains.resume.services.parser import transcribe_pages_with_vision
from realmock.domains.resume.services.text_extract import extract_text_from_file
from realmock.domains.resume.services.render import render_pdf_pages_as_data_urls
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.core.errors import raise_error
from realmock.platform.services.pipeline.config import get_stage_config_for_runtime

logger = logging.getLogger(__name__)

# Re-export lookup helpers so existing callers/tests keep a stable import path.
__all__ = ["extract_resume_text", "find_resume_file", "find_resume_files"]


async def extract_resume_text(
    file_path: Path,
    ext: str,
    llm: LLMClient,
    db: Session,
) -> str:
    """Extract résumé text; if an image-based PDF has no text layer, fall back to transcription by a vision model.

    - Extraction/transcription error → A1004 (file parsing failed);
    - Image-based PDF with no vision model bound to the chat task → A1006 (reject explicitly;
      silently storing empty text would make the AI evaluation treat it as a "blank résumé");
    - Still no text after fallback → A1004.
    """
    try:
        # pypdf (up to 50 pages) / python-docx (up to 30MB uncompressed) parsing
        # is synchronous CPU+disk work; keep it off the event loop so in-flight
        # SSE streams sharing the loop do not stall (same discipline as the
        # fitz render below). Raises from the worker propagate unchanged.
        raw_text = await asyncio.to_thread(extract_text_from_file, file_path, ext)
    except Exception as e:
        logger.warning("Resume parsing failed: %s", e)
        raise_error("A1004", cause=e)

    if raw_text.strip():
        return raw_text
    if ext != "pdf":
        # Silently storing empty text would make the AI evaluation treat it as a blank resume; reject explicitly.
        raise_error("A1004")

    vision_cfg = get_stage_config_for_runtime(db, "reason")
    if not (llm.api_key and vision_cfg.get("supports_vision")):
        raise_error("A1006")
    try:
        # Sync fitz rendering must not block the event loop (SSE heartbeats
        # share it); the semaphore inside still caps fitz concurrency at 2.
        page_images = await asyncio.to_thread(render_pdf_pages_as_data_urls, file_path)
        raw_text = await transcribe_pages_with_vision(page_images, llm)
    except Exception as e:
        logger.warning("Image PDF visual transcription failed: %s", e)
        raise_error("A1004", cause=e)
    if not raw_text.strip():
        raise_error("A1004")
    return raw_text
