"""Template helpers shared by vendor adapters: deep merge and placeholder substitution.

Used to combine (vendor def defaults) + (user extras overrides) into the final request,
and to substitute ``{{placeholder}}`` tokens in user-authored adapter templates.
"""

from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def deep_merge(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    """Recursively merge ``override`` into ``base`` and return a new dict.

    ``override`` wins on conflicts; nested dicts merge key-by-key so users can
    customize any single field without restating the whole template. Lists and
    scalars are replaced wholesale.
    """
    merged: dict[str, Any] = dict(base or {})
    for key, value in (override or {}).items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def fill_placeholders(value: Any, variables: dict[str, str]) -> Any:
    """Replace ``{{name}}`` tokens in every string of a nested structure.

    Unknown placeholders are left as-is so malformed templates surface in the
    vendor's error response instead of silently disappearing.
    """
    if isinstance(value, str):
        return _PLACEHOLDER.sub(
            lambda m: str(variables.get(m.group(1), m.group(0))), value
        )
    if isinstance(value, dict):
        return {k: fill_placeholders(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [fill_placeholders(v, variables) for v in value]
    return value


def get_dotted(payload: Any, path: str) -> Any:
    """Read a dotted path (e.g. ``data.audio``) from a decoded JSON payload."""
    current = payload
    for part in (path or "").split("."):
        if not part:
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


__all__ = ["deep_merge", "fill_placeholders", "get_dotted"]
