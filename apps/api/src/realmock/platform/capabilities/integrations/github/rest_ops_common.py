"""GitHub REST public auxiliary (error determination and paging clipping)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote


def _is_error(data: Any) -> bool:
    return isinstance(data, dict) and "error" in data


def _clamp_per_page(value: int, limit: int) -> int:
    return max(1, min(value, limit))


def _path_segment(value: str) -> str:
    """Percent-encode one model-supplied URL path segment.

    Tool arguments (owner/repo/username/branch) come from the model and are
    interpolated into api.github.com paths; without encoding, ``/`` ``..`` ``?``
    ``#`` could rewrite the endpoint being hit. Encoding keeps normal names
    byte-identical and neutralizes traversal/query characters.
    """
    return quote(str(value or ""), safe="")


def _content_path(value: str) -> str:
    """Encode a repository file path, preserving ``/`` as a real separator."""
    return quote(str(value or "").lstrip("/"), safe="/")
