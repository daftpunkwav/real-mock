"""On-disk lookup for stored resume uploads.

Responsibilities:
- Resolve ``{row_id}_{sanitized}`` first, then legacy ``{8-hex}_{sanitized}``
- Never prefix-match (row-id collisions) or suffix-match (similar stems)

Must not import parsers, LLM clients, or FastAPI routers. Persistence
(delete/unlink) and HTTP file streaming both depend on this module so the
store does not pull in the extraction/LLM stack.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from realmock.platform.models import Resume
from realmock.platform.config import get_settings
from realmock.platform.core.security import assert_within_dir, sanitize_filename

logger = logging.getLogger(__name__)

# Legacy on-disk filename: {8-hex-digit uuid}_{sanitized_name}; current format is {row_id}_sanitized_name.
_LEGACY_NAME_RE = re.compile(r"[0-9a-f]{8}_(.+)", re.I)


def find_resume_files(resume: Resume) -> list[Path]:
    """Locate all candidates for an uploaded file.

    Return exact {id}_{sanitized} first; only then scan legacy UUID names.
    Sanitized names keep alphanumerics and underscores.
    """
    upload_dir = Path(get_settings().upload_dir).resolve()
    sanitized = sanitize_filename(resume.filename)
    try:
        exact = assert_within_dir(upload_dir / f"{resume.id}_{sanitized}", upload_dir)
        if exact.is_file():
            return [exact]
        found: list[Path] = []
        for path in upload_dir.glob(f"*_{sanitized}"):
            match = _LEGACY_NAME_RE.fullmatch(path.name)
            if not match or match.group(1) != sanitized:
                continue
            assert_within_dir(path, upload_dir)
            if path.is_file():
                found.append(path)
        return found
    except Exception:
        logger.debug("Failed to locate resume file id=%s", resume.id, exc_info=True)
        return []


def find_resume_file(resume: Resume) -> Path | None:
    """Return the first stored-file candidate, or None when missing."""
    files = find_resume_files(resume)
    return files[0] if files else None
