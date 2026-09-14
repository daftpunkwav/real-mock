"""Shared helpers for translating LLM protocols.

Pure functions shared by protocol conversion modules (anthropic / responses / response extraction)
(``_json_arguments``, ``_headers``); contains no protocol-specific logic.
"""

from __future__ import annotations

import json
from typing import Any

from realmock.platform.core.constants import LLMProtocol


def _json_arguments(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value or {}, ensure_ascii=False)
    except TypeError:
        return "{}"


def _headers(api_key: str, protocol: str) -> dict[str, str]:
    headers = {
        "api-key": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    return headers


__all__ = ["_json_arguments", "_headers"]
