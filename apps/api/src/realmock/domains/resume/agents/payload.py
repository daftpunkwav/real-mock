"""Build the first user message for resume review: vision pages or parsed text.

PDF + vision: attach rendered page images so the model sees layout/type.
DOCX/MD/TXT, or a model without vision: point the model at resume_* tools
and include a short overview only — never dump the full raw body here.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from realmock.domains.resume.prompts import review_intro_instruction
from realmock.domains.resume.schemas.limits import MAX_VISION_PAGES
from realmock.domains.resume.services.files import find_resume_file
from realmock.domains.resume.services.render import render_pdf_pages_as_data_urls
from realmock.platform.capabilities.ai.agent.tools.resume import (
    ResumeSnapshot,
    _contact_bundle,
    _github_urls_from_text,
)
from realmock.platform.capabilities.ai.context.estimation import select_vision_urls
from realmock.platform.capabilities.ai.llm.defaults import resolve_context_window
from realmock.platform.models import Resume

logger = logging.getLogger(__name__)


def _overview_text(snapshot: ResumeSnapshot) -> str:
    parsed = snapshot.parsed if isinstance(snapshot.parsed, dict) else {}
    contact = _contact_bundle(parsed, snapshot.raw_text)
    github = [str(u).strip() for u in (parsed.get("github_urls") or [])]
    github = [u for u in github if u] or _github_urls_from_text(snapshot.raw_text)
    brief = {
        "filename": snapshot.filename,
        "file_type": snapshot.file_type,
        "name": parsed.get("name") or "",
        "target_role": parsed.get("target_role") or "",
        "skills": (parsed.get("skills") or [])[:16],
        "project_names": [
            (p.get("name") if isinstance(p, dict) else str(p))
            for p in (parsed.get("projects") or [])[:8]
        ],
        "parse_degraded": bool(parsed.get("parse_degraded")),
        "layout_notes": (snapshot.layout_notes or "")[:400],
        "has_visual_pages": snapshot.has_visual_pages,
        "contact": {
            "email": contact["email"],
            "phone": contact["phone"],
            "city": contact["city"],
            "github_urls": github[:4],
        },
    }
    return (
        review_intro_instruction()
        + f"Compact parsed map:\n{json.dumps(brief, ensure_ascii=False)}"
    )


async def build_review_user_message(
    resume: Resume,
    snapshot: ResumeSnapshot,
    *,
    supports_vision: bool,
    context_window: int | None = None,
    calibration: str = "",
) -> dict[str, Any]:
    """Return one user message (string or multimodal content list).

    ``calibration`` is a prebuilt prior-version reference block (empty for
    same-file re-reviews, which score from current evidence alone); this module
    does not query the store. The PDF page render runs in a worker thread so
    the event loop is never blocked by the synchronous ``fitz`` call.
    """
    intro = _overview_text(snapshot)
    extra = calibration.strip()
    if extra:
        intro = f"{intro}\n{extra}"
    if snapshot.file_type.lower() == "pdf" and not supports_vision:
        snapshot.visual_status = "no_vision"
    if not supports_vision or snapshot.file_type.lower() != "pdf":
        if snapshot.file_type.lower() in {"docx", "doc"}:
            intro += (
                "\nOriginal file is Word. Page images are unavailable; judge layout from "
                "heading markers / tables in resume_get_section and layout_notes."
            )
        return {"role": "user", "content": intro}

    path = find_resume_file(resume)
    if path is None:
        logger.warning("Vision review skipped: original PDF missing id=%s", resume.id)
        snapshot.has_visual_pages = False
        snapshot.visual_status = "missing_file"
        return {
            "role": "user",
            "content": intro + "\nVisual render unavailable (file missing); use resume tools.",
        }
    try:
        urls = await asyncio.to_thread(render_pdf_pages_as_data_urls, path, max_pages=MAX_VISION_PAGES)
    except Exception as exc:
        logger.warning("PDF page render failed id=%s: %s", resume.id, exc)
        snapshot.has_visual_pages = False
        snapshot.visual_status = "render_failed"
        return {
            "role": "user",
            "content": intro + "\nVisual render failed; use resume tools for content and structure.",
        }
    urls = select_vision_urls(urls, resolve_context_window(context_window))
    if not urls:
        snapshot.has_visual_pages = False
        snapshot.visual_status = "filtered"
        return {"role": "user", "content": intro}

    snapshot.has_visual_pages = True
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": intro + f"\n{len(urls)} original PDF page image(s) follow. Judge layout and typography from them.",
        }
    ]
    content.extend({"type": "image_url", "image_url": {"url": url}} for url in urls)
    return {"role": "user", "content": content}


__all__ = ["build_review_user_message"]
