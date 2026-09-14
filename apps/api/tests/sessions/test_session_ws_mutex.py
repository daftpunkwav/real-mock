"""Session fix: allow only one active WebSocket per session_id; a new connection evicts the old one."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_ws() -> MagicMock:
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_claim_kicks_old_connection() -> None:
    from realmock.domains.interview.realtime import ws_handler as ws_mod

    ws_mod.reset_session_registry_for_tests()
    old = ws_mod.InterviewWSHandler(_mock_ws(), session_id=7)
    new = ws_mod.InterviewWSHandler(_mock_ws(), session_id=7)

    await ws_mod.claim_session_connection(old)
    await ws_mod.claim_session_connection(new)

    assert old._superseded is True
    assert new._superseded is False
    assert ws_mod.active_handlers_for_tests()[7] is new
    old.ws.close.assert_awaited()

    await ws_mod.release_session_connection(old)
    assert ws_mod.active_handlers_for_tests()[7] is new
    await ws_mod.release_session_connection(new)
    assert 7 not in ws_mod.active_handlers_for_tests()


@pytest.mark.asyncio
async def test_image_base64_oversize_dropped() -> None:
    """Oversized image_base64 is discarded at the WS turn entry point (aligned with the HTTP max_length)."""
    from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler, _IMAGE_BASE64_MAX_LEN
    from realmock.domains.interview.services.interview.events import EventKind, StreamEvent

    handler = InterviewWSHandler(_mock_ws(), session_id=1)
    captured: dict = {}

    class _Runner:
        async def stream_turn(self, text, db, *, face=None, image_b64=None):
            captured["image_b64"] = image_b64
            yield StreamEvent.make_turn_done(
                content="ok",
                phase_id="p",
                is_complete=False,
                phase_changed=False,
                emotion="neutral",
            )

    handler.ctx.runner = _Runner()
    handler.ctx.orchestrator = MagicMock()
    handler.ctx.orchestrator.snapshot.face_analysis = {}
    handler.ctx.orchestrator.snapshot.merge_face = MagicMock()

    huge = "A" * (_IMAGE_BASE64_MAX_LEN + 10)
    events = []
    async for ev in handler._consume_runner_turn(
        "hello", {"image_base64": huge}, db=MagicMock()
    ):
        events.append(ev)

    assert captured["image_b64"] is None
    assert events and events[-1].kind == EventKind.TURN_COMPLETE
