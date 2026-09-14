"""Parse tool observations for the resume-review live UI.

Extracts search hosts from web_search JSON and scrubs secrets from tool args.
Tool results are passed through unclipped so the live UI shows the full text.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

_SEARCH_TOOL_NAMES = frozenset({"web_search"})
_SECRET_ARG_KEYS = frozenset({"api_key", "token", "authorization", "secret", "password", "bearer"})


def search_hosts_from_observation(name: str, result: str) -> list[str]:
    """Hostnames from a web_search observation, unique, first-seen order."""
    if name not in _SEARCH_TOOL_NAMES:
        return []
    try:
        data = json.loads(result or "")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    hosts: list[str] = []
    seen: set[str] = set()
    hits = data.get("results")
    if not isinstance(hits, list):
        return []
    for hit in hits:
        url = ""
        if isinstance(hit, dict):
            url = str(hit.get("url") or "")
        elif isinstance(hit, str):
            url = hit
        host = _host_of(url)
        if not host or host in seen:
            continue
        seen.add(host)
        hosts.append(host)
    return hosts[:12]


def _host_of(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.netloc or parsed.path.split("/")[0]).lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def public_tool_args(args: dict[str, Any]) -> dict[str, Any]:
    """Shallow copy of tool args for the live UI; drop secret keys."""
    out: dict[str, Any] = {}
    for key, value in (args or {}).items():
        if key.lower() in _SECRET_ARG_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value if not isinstance(value, str) else value[:500]
        elif isinstance(value, dict):
            blob = json.dumps(value, ensure_ascii=False)
            out[key] = blob[:500]
        elif isinstance(value, list):
            out[key] = value[:12]
    return out


__all__ = [
    "public_tool_args",
    "search_hosts_from_observation",
]
