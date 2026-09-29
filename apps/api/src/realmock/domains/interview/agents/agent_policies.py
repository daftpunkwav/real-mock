"""Declared per-agent budget policies (LangGraph `RetryPolicy`/`TimeoutPolicy`
semantics, borrowed as a declaration table instead of a runtime).

Every wait/retry/cap number an interview agent lives under is declared here so
tuning "urgency tiers" is a table edit, not a code hunt:

- live-interview agents (candidate waiting): generous ROUNDS, tight timeouts,
  aggressive breaker — a hung tool fails fast and the model reroutes;
- background agents (nobody waiting): generous wall clocks, accuracy first.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolGuardPolicy:
    """Per-call tool resilience (mirrors :mod:`tool_guard` defaults)."""

    timeout_sec: float = 20.0
    attempts: int = 1
    circuit_streak: int = 2
    circuit_ttl_sec: float = 600.0
    timeout_override_min: float = 5.0
    # Cap on the model-supplied per-call extension: a candidate is waiting,
    # so even a "slow page" may not stall a reply for minutes.
    timeout_override_max: float = 60.0


@dataclass(frozen=True)
class LoopPolicy:
    """One agent loop: round cap plus the whole-loop wall-clock budget."""

    max_rounds: int
    budget_seconds: float
    guard: ToolGuardPolicy = ToolGuardPolicy()


@dataclass(frozen=True)
class BackgroundPolicy:
    """Background side-agents: never gate the reply, bounded anyway."""

    shadow_seconds: float = 90.0


@dataclass(frozen=True)
class CompactionPolicy:
    """Step-boundary compaction thresholds and retry ladder."""

    skip_below_tokens: int = 20_000
    max_attempts: int = 3
    retry_delays: tuple[float, ...] = (0.0, 30.0, 120.0)
    #: Termination for the accumulate-and-retry chain: after this many failed
    #: boundary rounds the segment is dead-lettered (raw dialogue stays
    #: verbatim) instead of retrying forever and growing the merged input.
    max_failed_rounds: int = 3
    budget_seconds: float = 700.0
    keep_recent_summaries: int = 6
    rollup_token_threshold: int = 300_000
    rollup_count_threshold: int = 12


#: The interviewer loop is live but evidence-driven: up to 8 rounds of tools
#: inside a 600s turn budget, tools fail fast within each round.
INTERVIEWER_LOOP = LoopPolicy(max_rounds=8, budget_seconds=600.0)

#: The reference-hint loop is assistance on the room's critical path.
HINT_LOOP = LoopPolicy(max_rounds=2, budget_seconds=60.0)

#: Background evaluators (shadow pipeline).
BACKGROUND = BackgroundPolicy()

#: Step-boundary compaction state machine.
COMPACT = CompactionPolicy()

__all__ = [
    "BACKGROUND",
    "COMPACT",
    "HINT_LOOP",
    "INTERVIEWER_LOOP",
    "BackgroundPolicy",
    "CompactionPolicy",
    "LoopPolicy",
    "ToolGuardPolicy",
]
