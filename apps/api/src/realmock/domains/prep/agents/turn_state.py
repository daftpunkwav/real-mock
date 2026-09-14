"""Per-turn mutable state for the prep agent.

The prep agent is rebuilt per request, but each user turn resets its
loop-local state. This value object isolates that state from the agent's
session-level fields so the orchestration layer (chat.py) can reset and inspect
it without reaching into private agent internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from realmock.platform.capabilities.ai.context.options import CompactionOptions


@dataclass
class TurnState:
    """Mutable container for one turn's policy, toolset, and compaction bookkeeping."""

    #: Per-turn compaction policy (intensity/directive/retain) resolved from
    #: caller options or session defaults.
    policy: CompactionOptions = field(default_factory=CompactionOptions)
    #: True once the agent-invoked compact_context tool runs this turn.
    compact_used: bool = False
    #: True once search_tools has loaded secondary schemas this turn.
    expanded: bool = False
    #: The frozen tool declaration list handed to the loop; mid-turn expansion
    #: only appends, so the cached prefix head stays stable.
    tools: list[dict[str, Any]] | None = None
    #: Mid-turn compaction result persisted while the loop ran on a working copy.
    #: finalize() merges the loop tail back onto this base.
    mid_turn_base: list[dict[str, Any]] | None = None
    #: Metrics from the last mid-turn compaction (surfaced as SSE compaction event).
    mid_turn_report: dict[str, Any] | None = None
    #: Length of the working message list at loop entry; used to splice the
    #: post-compaction tail back onto persisted history.
    pre_loop_len: int | None = None
    #: Successful memory_write dispatches this turn (budget guard against spam).
    memory_writes: int = 0

    def reset(self, options: CompactionOptions | None = None) -> None:
        """Reset all fields for a new turn; preserve nothing from the previous turn.

        Args:
            options: Turn compaction policy (None builds default options).
        """
        self.policy = options or CompactionOptions()
        self.compact_used = False
        self.expanded = False
        self.tools = None
        self.mid_turn_base = None
        self.mid_turn_report = None
        self.pre_loop_len = None
        self.memory_writes = 0


__all__ = ["TurnState"]
