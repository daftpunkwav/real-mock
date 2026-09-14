"""File name cleaning, path traversal prevention and extension magic number checking."""

from __future__ import annotations

import re
from pathlib import Path

# Only keep ASCII alphanumeric + common delimiters, replace others with underscores
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_FILENAME_LEN = 120

# File header signatures of common binary containers (extension ↔ used for basic magic number sniffing)
_MAGIC_BYTES: dict[str, list[bytes]] = {
    "pdf": [b"%PDF-"],
    "docx": [b"PK\x03\x04"],  # zip container
    "doc": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],  # OLE
}


def sanitize_filename(name: str) -> str:
    """Sanitize a filename, retaining only safe characters.

    - Take only the basename after the last path separator
    - Remove non-printable/control characters
    - Retain only [A-Za-z0-9._-]
    - Limit the length to 120
    """
    if not name:
        return "file"

    # Remove path part (Windows/POSIX)
    base = name.replace("\\", "/").split("/")[-1]
    base = base.strip().strip(".") or "file"
    cleaned = _SAFE_FILENAME_RE.sub("_", base)
    # Prevent only "."
    if not cleaned or set(cleaned) <= {"."}:
        cleaned = "file"
    if len(cleaned) > _MAX_FILENAME_LEN:
        stem, dot, suffix = cleaned.rpartition(".")
        if dot and 0 < len(suffix) < _MAX_FILENAME_LEN - 1:
            stem = stem[: _MAX_FILENAME_LEN - len(suffix) - 1]
            cleaned = f"{stem}.{suffix}"
        else:
            cleaned = cleaned[:_MAX_FILENAME_LEN]
    # When the suffix is ​​too long, negative slicing will preserve the overlong result and eventually truncate it unconditionally.
    return cleaned[:_MAX_FILENAME_LEN]


def sniff_extension(head: bytes, ext: str) -> bool:
    """Validate the extension against the file header to prevent extension spoofing.

    Binary formats are checked against magic bytes; unregistered formats (plain text such as md/txt) are not strictly validated.
    """
    sigs = _MAGIC_BYTES.get(ext)
    if not sigs:
        return True
    return any(head.startswith(sig) for sig in sigs)


def assert_within_dir(path: Path, root: Path) -> Path:
    """Ensure ``path`` is under ``root`` (path traversal protection).

    Returns the normalized path; raises ``ValueError`` if it escapes the root.
    """
    root_resolved = root.resolve()
    path_resolved = (root_resolved / path).resolve() if not path.is_absolute() else path.resolve()
    try:
        path_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"Path out of bounds: {path}") from exc
    return path_resolved
