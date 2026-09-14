"""Per-turn toolset policy for the prep agent.

Extracted from :mod:`agent`: which tools the model may call in one turn, and
how on-demand (secondary-tier) schemas join the live declaration list.

The frozen list is handed to the tool loop by reference — mid-turn expansion
only appends, so the cached prefix head never reorders (see
:func:`freeze_turn_tools`). The complete declaration set (``ask_user`` +
domain registry) is also composed here as :data:`PREP_TOOL_DEFINITIONS`.
"""

from __future__ import annotations

from typing import Any

from .ask_user import ASK_USER_TOOL
from .tools import COMPACT_TOOL_DEFINITION
from .tools import PREP_TOOL_DEFINITIONS as DOMAIN_TOOL_DEFINITIONS
from .tools import SECONDARY_DEFINITIONS
from .tools import TOOL_REGISTRY, TOOL_TIER_SECONDARY
from .tools import preload_secondary, tool_available
from .turn_state import TurnState

#: Complete toolset handed to the model = ask_user + domain tool registry.
PREP_TOOL_DEFINITIONS: list[dict[str, Any]] = [ASK_USER_TOOL, *DOMAIN_TOOL_DEFINITIONS]

#: Per-turn memory_write budget: the LLM owns dedup decisions, this only stops
#: runaway loops from spamming the store. Distinct facts should be batched
#: into fewer calls.
MAX_MEMORY_WRITES_PER_TURN = 2


def freeze_turn_tools(
    *,
    resume_id: int | None,
    user_text: str = "",
    turn_state: TurnState,
) -> list[dict[str, Any]]:
    """Freeze the per-turn model toolset: tier-1 + turn-relevant tools, then compact.

    Secondary-tier specs stay out of the initial declarations UNLESS a
    name-gated signal matches (repo talk preloads github tools) — decided
    once at turn start, frozen for the round, so the cached prefix head
    never reorders. Anything else secondary loads through ``search_tools``.
    The returned list is stored as ``turn_state.tools`` and handed to the
    loop by reference — mid-turn expansion only appends.

    Args:
        resume_id: Session resume id, used by availability/signal gates.
        user_text: Latest user input, used for name-gated tool signals.
        turn_state: Per-turn state receiving the frozen toolset.

    Returns:
        The frozen turn toolset (also stored on ``turn_state``).
    """
    primary: list[dict[str, Any]] = []
    preloaded: list[dict[str, Any]] = []
    for item in [ASK_USER_TOOL, *DOMAIN_TOOL_DEFINITIONS]:
        name = ""
        try:
            name = str((item.get("function") or {}).get("name") or "")
        except Exception:
            name = ""
        if not name:
            continue
        spec = TOOL_REGISTRY.get(name)
        if spec is not None and spec.tier == TOOL_TIER_SECONDARY:
            # On-demand tier: preload only on a matched signal gate (repo
            # talk); pure on-demand tools wait for search_tools.
            if preload_secondary(name, user_text, resume_id):
                preloaded.append(item)
            continue
        if not tool_available(name, user_text, resume_id):
            continue
        primary.append(item)
    declared = [*primary, *preloaded]
    # Static compact-tool declaration: the live usage estimate moved to the
    # per-turn [Context usage] system suffix (build_working_context) — a
    # per-turn tool description would sit at the head of the provider
    # request and invalidate the whole prompt-cache prefix every turn.
    declared.append(COMPACT_TOOL_DEFINITION)
    turn_state.tools = declared
    return declared


def expand_turn_tools(*, turn_state: TurnState, selected: list[str]) -> list[str]:
    """Append on-demand schemas to the live turn toolset. Returns names added."""
    added: list[str] = []
    if turn_state.tools is None:
        return added
    try:
        present = {
            str((item.get("function") or {}).get("name") or "")
            for item in turn_state.tools
        }
    except Exception:
        present = set()
    for name in selected:
        if name in present or name not in SECONDARY_DEFINITIONS:
            continue
        turn_state.tools.append(SECONDARY_DEFINITIONS[name])
        present.add(name)
        added.append(name)
    return added


__all__ = [
    "MAX_MEMORY_WRITES_PER_TURN",
    "PREP_TOOL_DEFINITIONS",
    "expand_turn_tools",
    "freeze_turn_tools",
]
