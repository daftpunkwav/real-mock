"""Plain-text extraction from resume files under catalog resource limits.

Responsibilities:
- Extract text from PDF (page cap) / DOCX (zip-bomb guards, heading markers,
  capped tables) / MD / TXT, truncated to ``MAX_EXTRACTED_CHARS``

Pure file parsing: no LLM, no ORM, no network. LLM transcription and
structured parsing live in ``parser``. Must not import FastAPI or ORM.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from realmock.domains.resume.schemas.limits import (
    MAX_DOCX_TABLE_ROWS,
    MAX_DOCX_TABLES,
    MAX_DOCX_UNCOMPRESSED_BYTES,
    MAX_DOCX_ZIP_ENTRIES,
    MAX_EXTRACTED_CHARS,
    MAX_PARAGRAPHS,
    MAX_PDF_PAGES,
)

logger = logging.getLogger(__name__)


def _truncate(text: str) -> str:
    if len(text) <= MAX_EXTRACTED_CHARS:
        return text
    return text[:MAX_EXTRACTED_CHARS]


def truncate_text(text: str) -> str:
    """Cap text to ``MAX_EXTRACTED_CHARS`` (shared with vision transcription)."""
    return _truncate(text)


def _assert_docx_zip_safe(file_path: Path) -> None:
    """Verify the number of DOCX (ZIP) entries and the decompressed volume to prevent zip bombs."""
    with zipfile.ZipFile(file_path, "r") as zf:
        infos = zf.infolist()
        if len(infos) > MAX_DOCX_ZIP_ENTRIES:
            raise ValueError(
                f"Too many DOCX entries ({len(infos)} > {MAX_DOCX_ZIP_ENTRIES})"
            )
        total = 0
        for info in infos:
            total += max(0, int(info.file_size))
            if total > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise ValueError("The volume of DOCX after decompression exceeds the upper limit.")


def _heading_prefix(style_name: str) -> str:
    lower = (style_name or "").lower()
    if "heading 1" in lower or lower == "title":
        return "# "
    if "heading 2" in lower:
        return "## "
    if "heading" in lower:
        return "### "
    return ""


def _extract_docx_structured(file_path: Path) -> str:
    """Extract paragraphs (with heading markers) and tables so Agents keep layout cues."""
    doc = Document(str(file_path))
    parts: list[str] = []
    for para in doc.paragraphs[:MAX_PARAGRAPHS]:
        text = (para.text or "").strip()
        if not text:
            continue
        style = ""
        try:
            style = para.style.name if para.style is not None else ""
        except Exception:
            logger.debug("DOCX paragraph style unreadable", exc_info=True)
            style = ""
        parts.append(_heading_prefix(style) + text)

    for table in list(doc.tables)[:MAX_DOCX_TABLES]:
        rows: list[str] = []
        try:
            table_rows = list(table.rows)[:MAX_DOCX_TABLE_ROWS]
        except Exception:
            logger.debug("DOCX table rows unreadable", exc_info=True)
            continue
        for row in table_rows:
            try:
                cells = [(cell.text or "").strip() for cell in row.cells]
            except Exception:
                logger.debug("DOCX table row unreadable", exc_info=True)
                continue
            line = " | ".join(cell for cell in cells if cell)
            if line:
                rows.append(line)
        if rows:
            parts.append("[table]\n" + "\n".join(rows))
    return "\n".join(parts)


def extract_text_from_file(file_path: Path, file_type: str) -> str:
    """Extract plain text from PDF/DOC/DOCX/MD/TXT."""
    suffix = file_type.lower()

    if suffix == "pdf":
        reader = PdfReader(str(file_path))
        pages = reader.pages
        if len(pages) > MAX_PDF_PAGES:
            raise ValueError(f"PDF has too many pages ({len(pages)} > {MAX_PDF_PAGES})")
        text = "\n".join((page.extract_text() or "") for page in pages)
        return _truncate(text)

    if suffix in ("docx", "doc"):
        _assert_docx_zip_safe(file_path)
        return _truncate(_extract_docx_structured(file_path))

    # md/txt/other text formats
    raw = file_path.read_text(encoding="utf-8", errors="ignore")
    return _truncate(raw)


__all__ = ["extract_text_from_file", "truncate_text"]
