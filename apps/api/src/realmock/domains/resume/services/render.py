"""PDF page rendering: original-file preview PNGs and vision-transcription images.

Responsibilities:
- Deterministic PDF page → PNG (preview zoom and vision zoom)
- Clamp oversized page boxes so a malicious page box cannot explode RAM

Callers: file routes (preview) and extract (vision fallback). Limits live in
``schemas.limits``. Must not extract text or call an LLM.
"""

from __future__ import annotations

import base64
import threading
from pathlib import Path
from typing import Any

from realmock.domains.resume.schemas.limits import (
    MAX_RENDER_PX,
    MAX_VISION_PAGES,
    PAGE_PREVIEW_ZOOM,
    PDF_RENDER_ZOOM,
    RENDER_CONCURRENCY,
)

_RENDER_SEMAPHORE = threading.Semaphore(RENDER_CONCURRENCY)


def pdf_page_count(file_path: Path) -> int:
    """Returns the number of PDF pages (for paging preview of the original file)."""
    import fitz  # Delayed import: only PDF rendering path requires PyMuPDF

    doc = fitz.open(file_path)
    try:
        return len(doc)
    finally:
        doc.close()


def _clamped_zoom(page: Any, zoom: float) -> float:
    """Calculate zoom from the per-side pixel limit: do not expand oversized page boxes (posters/malicious inputs) in memory.

    ``page`` is a lazily imported ``fitz.Page``.
    """
    longest_pt = max(page.rect.width, page.rect.height, 1.0)
    return min(zoom, MAX_RENDER_PX / longest_pt)


def render_pdf_page_png(
    file_path: Path, page_no: int, *, zoom: float = PAGE_PREVIEW_ZOOM
) -> bytes:
    """Render the specified page (1-based) as PNG bytes (for paginated preview of the original file).

    An out-of-range page number raises ValueError, which the route layer translates into a domain error.
    """
    import fitz  # Delayed import: only PDF rendering path requires PyMuPDF

    doc = fitz.open(file_path)
    try:
        if not 1 <= page_no <= len(doc):
            raise ValueError(f"Page number out of bounds: {page_no}(common {len(doc)} Page)")
        page = doc[page_no - 1]
        with _RENDER_SEMAPHORE:
            effective = _clamped_zoom(page, zoom)
            pix = page.get_pixmap(matrix=fitz.Matrix(effective, effective))
            return pix.tobytes("png")
    finally:
        doc.close()


def render_pdf_pages_as_data_urls(
    file_path: Path,
    *,
    max_pages: int = MAX_VISION_PAGES,
) -> list[str]:
    """Render a PDF page by page as PNG data URLs for transcription by a vision model (fallback for image-only PDFs).

    When the page limit is exceeded, only the first ``max_pages`` pages are used; rendering failures raise the original exception for the caller to handle.
    """
    import fitz  # Delayed import: Only image-type PDF backend paths require PyMuPDF

    doc = fitz.open(file_path)
    try:
        urls: list[str] = []
        for i in range(min(len(doc), max_pages)):
            page = doc[i]
            with _RENDER_SEMAPHORE:
                effective = _clamped_zoom(page, PDF_RENDER_ZOOM)
                png = page.get_pixmap(matrix=fitz.Matrix(effective, effective)).tobytes("png")
            urls.append(f"data:image/png;base64,{base64.b64encode(png).decode()}")
        return urls
    finally:
        doc.close()
