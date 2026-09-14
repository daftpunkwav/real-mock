"""Time-consuming wrapper for routing layer connectivity testing."""

from __future__ import annotations

import time


async def run_timed_stage_test(stage_test) -> dict:
    """Timed wrapper: runs stage test and records latency_ms for frontend display."""
    start = time.perf_counter()
    result = await stage_test
    result["latency_ms"] = int((time.perf_counter() - start) * 1000)
    return result
