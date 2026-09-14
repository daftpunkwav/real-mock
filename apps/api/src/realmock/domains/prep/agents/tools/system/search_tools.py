"""On-demand tool discovery: search secondary catalog and load schemas mid-turn."""

from __future__ import annotations

import json
from typing import Any

from realmock.domains.prep.agents.tools.spec import SearchHits, ToolSpec
from realmock.platform.capabilities.ai.agent import WorkingMemory

#: Max candidates returned per search call.
_SEARCH_MAX_RESULTS = 5


def _secondary_catalog() -> dict[str, ToolSpec]:
    """Lazy registry read (avoids import-time cycle with registry assembly)."""
    from realmock.domains.prep.agents.tools.registry import SECONDARY_TOOLS

    return SECONDARY_TOOLS


def _first_sentence(text: str) -> str:
    """One-line summary of a description (first sentence, bounded)."""
    flat = " ".join(str(text or "").split())
    for sep in (". ", "。", ".\n"):
        if sep in flat:
            flat = flat.split(sep, 1)[0]
            break
    return flat[:160].rstrip(". ")


def search_specs(query: str, limit: int = _SEARCH_MAX_RESULTS) -> list[ToolSpec]:
    """Rank secondary tools by name, keyword, then description match.

    Scoring is intentionally transparent: exact name hit (3) beats keyword
    hit (2) beats description hit (1); ties keep registry order (stable).
    Keyword matching runs both directions so multi-character Chinese queries
    ("记忆标签") still hit single-word aliases ("记忆"). Never raises.
    """
    try:
        catalog = _secondary_catalog()
    except Exception:
        return []
    needle = str(query or "").strip().lower()
    if not needle:
        return []
    ranked: list[tuple[int, int, ToolSpec]] = []
    for order, spec in enumerate(catalog.values()):
        if not spec.name:
            continue
        score = 0
        try:
            if needle in spec.name.lower():
                score = 3
            elif any(kw.lower() in needle or needle in kw.lower() for kw in spec.keywords if kw):
                score = 2
            elif needle in spec.description.lower():
                score = 1
        except Exception:
            continue
        if score:
            ranked.append((score, order, spec))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [spec for _, _, spec in ranked[: max(1, limit)]]


def mini_spec(spec: ToolSpec) -> dict[str, Any]:
    """Compact candidate card: name, one-line summary, and parameter names only."""
    properties = spec.parameters.get("properties", {}) if isinstance(spec.parameters, dict) else {}
    return {
        "name": spec.name,
        "summary": _first_sentence(spec.description),
        "params": sorted(str(k) for k in properties.keys()),
    }


async def run_search_tools(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    """Find on-demand tools by keyword; optionally select some to load now.

    Single-call semantics: ``select`` names full schemas for the loop, which
    appends them to this turn's toolset (next round callable). Unknown names
    are reported with the valid catalog instead of failing.
    """
    del memory
    try:
        catalog = _secondary_catalog()
    except Exception:
        catalog = {}
    query = str(args.get("query", "") or "")
    raw_select = args.get("select", [])
    select = [str(n) for n in raw_select] if isinstance(raw_select, list) else []
    candidates = search_specs(query)
    loaded = [n for n in select[:_SEARCH_MAX_RESULTS] if n in catalog]
    unknown = [n for n in select[:_SEARCH_MAX_RESULTS] if n not in catalog]
    payload: dict[str, Any] = {
        "candidates": [mini_spec(spec) for spec in candidates],
        "loaded": loaded,
        "unknown": unknown,
    }
    if unknown:
        payload["catalog"] = sorted(catalog)
    return json.dumps(payload, ensure_ascii=False), []


SEARCH_TOOLS_SPEC = ToolSpec(
    name="search_tools",
    description=(
        "Find on-demand tools by keyword when the declared tools lack what this "
        "turn needs (repository tools, memory query tools). Returns matching "
        "candidates with one-line summaries; names passed in select are loaded "
        "immediately and become callable next round, at most once per turn."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keywords for the capability needed, e.g. repo file, memory tags",
            },
            "select": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Candidate names to load now (optional)",
            },
        },
        "required": ["query"],
    },
    handler=run_search_tools,
)


__all__ = ["SEARCH_TOOLS_SPEC", "mini_spec", "run_search_tools", "search_specs"]
