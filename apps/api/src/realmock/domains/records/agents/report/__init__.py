"""ReAct deep-report agent package: ledger tools, two stages, normalization."""

from __future__ import annotations

from .agent import (
    DeepReportAgent,
    MAX_PARALLEL_BATCHES,
    REPORT_TIME_BUDGET_SECONDS,
    TURNS_PER_BATCH,
    build_context_specs,
    split_turn_ids,
)

__all__ = [
    "DeepReportAgent",
    "MAX_PARALLEL_BATCHES",
    "REPORT_TIME_BUDGET_SECONDS",
    "TURNS_PER_BATCH",
    "build_context_specs",
    "split_turn_ids",
]
