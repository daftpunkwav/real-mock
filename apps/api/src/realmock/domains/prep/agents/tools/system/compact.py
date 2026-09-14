"""Compaction tool declaration: agent-invoked context folding.

Declared here so the model sees one tool schema source, but intentionally NOT
in the registry: execution rewrites agent history and must run inside the turn
loop (:func:`round_compaction.compact_current_round`, reached via
``PrepAgent._compact_current_round``), which plain handlers cannot reach.
"""

from __future__ import annotations

from typing import Any

from realmock.domains.prep.agents.tools.spec import SearchHits, ToolSpec
from realmock.platform.capabilities.ai.agent import WorkingMemory


async def run_compact_out_of_loop(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    """Fallback for out-of-loop direct dispatch (never fires in the turn loop)."""
    del args, memory
    return "compact_context runs inside the turn loop only; it cannot fold history from here.", []


_COMPACT_TOOL_SPEC = ToolSpec(
    name="compact_context",
    description=(
        "Context compaction: fold older conversation turns into a sectioned summary to free context. "
        "Decide carefully before calling (at most once per turn): remaining space "
        "decides first — when plenty of context remains, do NOT compact even if the "
        "topic shifts; when space runs low, weigh relevance — compact only when "
        "earlier turns barely matter for the current task, and keep them when they "
        "are highly relevant. A still-short conversation is refused automatically. "
        "Never call it as the first action of a turn — think and work first "
        "(search, read, reason), and compact only when mid-turn pressure is "
        "real; an early blind fold burns context you have not used yet. "
        "Everything before the current user message is summarized (objectives, "
        "decisions, findings, to-dos are preserved) while the current turn stays "
        "verbatim. Tune the run with focus (what the summary must prioritize) and "
        "intensity (light keeps more verbatim detail, aggressive folds harder); "
        "both fall back to the session defaults when omitted."
    ),
    parameters={
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "One line on why compaction helps this turn (optional)",
            },
            "focus": {
                "type": "string",
                "description": (
                    "Compression focus for this run: what the summary must "
                    "prioritize, e.g. error stacks, confirmed plans, weak spots "
                    "(optional, max 500 chars)"
                ),
            },
            "intensity": {
                "type": "string",
                "enum": ["light", "balanced", "aggressive"],
                "description": (
                    "Compression amplitude for this run: light keeps more "
                    "verbatim detail, aggressive folds harder (optional)"
                ),
            },
        },
    },
    handler=run_compact_out_of_loop,
)

COMPACT_TOOL_DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": _COMPACT_TOOL_SPEC.name,
        "description": _COMPACT_TOOL_SPEC.description,
        "parameters": _COMPACT_TOOL_SPEC.parameters,
    },
}

COMPACT_TOOL_NAME = _COMPACT_TOOL_SPEC.name


__all__ = ["COMPACT_TOOL_DEFINITION", "COMPACT_TOOL_NAME"]
