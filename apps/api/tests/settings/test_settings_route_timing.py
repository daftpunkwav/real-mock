"""Route-timing tests for realmock.domains.settings.services.route_timing.

Covers: latency wrapper passthrough for timed stage tests.
Conventions: faked coroutine; no network or DB.
"""

from __future__ import annotations


def test_route_timing_wrapper() -> None:
    import asyncio

    from realmock.domains.settings.services.route_timing import run_timed_stage_test

    async def _fake():
        return {"success": True}

    async def _run():
        return await run_timed_stage_test(_fake())

    out = asyncio.run(_run())
    assert out["success"] is True
    assert "latency_ms" in out
