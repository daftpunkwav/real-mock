"""Silence-nudge timing: speech-end anchor, LLM wait clamp, probe cap + closing."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from realmock.domains.interview.realtime.control.silence_nudge import (
    NUDGE_PROBE_CAP,
    SilenceNudgeMixin,
    clamp_nudge_wait,
)
from realmock.domains.interview.realtime.core.events import TurnState


def test_clamp_nudge_wait_llm_wins_within_window():
    assert clamp_nudge_wait(12, 25) == 12
    assert clamp_nudge_wait(7, 25) == 7
    assert clamp_nudge_wait(60, 10) == 60


def test_clamp_nudge_wait_snaps_out_of_range():
    assert clamp_nudge_wait(70, 25) == 60
    assert clamp_nudge_wait(5, 25) == 7
    assert clamp_nudge_wait(120, 10) == 60


def test_clamp_nudge_wait_falls_back_to_default():
    assert clamp_nudge_wait(0, 25) == 25
    assert clamp_nudge_wait(0, 0) == 7
    assert clamp_nudge_wait(0, 999) == 60


def test_probe_cap_is_two():
    assert NUDGE_PROBE_CAP == 2


def _now() -> float:
    """Loop-clock now (monotonic; safe outside a running loop)."""

    async def _t() -> float:
        return asyncio.get_event_loop().time()

    return asyncio.run(_t())


def _mixin(**ctx_kwargs) -> SilenceNudgeMixin:
    now = _now()
    mixin = SilenceNudgeMixin()
    ctx = SimpleNamespace(
        session_id=1,
        turn_state=TurnState.USER_SPEAKING,
        tts_sent_this_turn=False,
        playback_done=SimpleNamespace(is_set=lambda: True),
        speech_end_at=now - 100.0,
        mic_opened_at=now - 100.0,
        nudge_grace_sec=5.0,
        nudge_cooldown_sec=10.0,
        last_wait_seconds=0.0,
        last_nudge_at=0.0,
        silence_probe_question="",
        silence_probe_seq=0,
        silence_capped=False,
        last_silence_probe="",
        agent=SimpleNamespace(plan=None, messages=[{"role": "assistant", "content": "Q?"}]),
        orchestrator=SimpleNamespace(),
    )
    for key, value in ctx_kwargs.items():
        setattr(ctx, key, value)
    mixin.ctx = ctx  # type: ignore[attr-defined]
    mixin.sent: list[tuple[str, dict]] = []  # type: ignore[attr-defined]

    async def send(event: str, **payload) -> None:
        mixin.sent.append((event, payload))  # type: ignore[attr-defined]

    async def set_turn(state) -> None:
        mixin.ctx.turn_state = state  # type: ignore[attr-defined]

    mixin.send = send  # type: ignore[method-assign]
    mixin.set_turn = set_turn  # type: ignore[method-assign]
    mixin._begin_playback_wait = lambda: asyncio.sleep(0)  # type: ignore[method-assign]
    mixin._speak_one = lambda text: asyncio.sleep(0)  # type: ignore[method-assign]
    mixin._open_mic_after_playback = lambda **kw: asyncio.sleep(0)  # type: ignore[method-assign]
    return mixin


def test_audio_in_flight_suppresses_nudge():
    """Never nudge over our own voice (backend guard, independent of client timing)."""
    mixin = _mixin(
        tts_sent_this_turn=True,
        playback_done=SimpleNamespace(is_set=lambda: False),
    )
    asyncio.run(mixin._on_silence_nudge())
    assert mixin.sent == []


def test_grace_counts_from_speech_end_not_mic_reentry():
    """STT-failure mic re-entries must not reset the clock (bug: grace loop)."""
    now = _now()
    mixin = _mixin(
        speech_end_at=now - 100.0,
        mic_opened_at=now,  # just re-stamped by a C2001 recovery
        silence_probe_question="Q?",
        silence_probe_seq=2,  # would close if grace passed
    )
    asyncio.run(mixin._on_silence_nudge())
    # Grace passed (anchor old) -> closing nudge spoken, not suppressed.
    assert [e for e, _ in mixin.sent] == ["silence_nudge"]
    assert mixin.ctx.silence_capped is True


def test_fresh_speech_end_holds_grace():
    now = _now()
    mixin = _mixin(speech_end_at=now, mic_opened_at=now - 100.0)
    asyncio.run(mixin._on_silence_nudge())
    assert mixin.sent == []


def test_capped_question_stays_quiet():
    """After the closing nudge, further silence wakes do nothing (no DB, no send)."""
    mixin = _mixin(
        silence_probe_question="Q?",
        silence_capped=True,
    )
    mixin._load_session = lambda db: (_ for _ in ()).throw(AssertionError("must not touch DB"))  # type: ignore[method-assign]
    asyncio.run(mixin._on_silence_nudge())
    assert mixin.sent == []


def test_cap_speaks_closing_nudge_once():
    """seq>=2 uncapped -> one closing nudge, then capped."""
    mixin = _mixin(
        silence_probe_question="Q?",
        silence_probe_seq=2,
    )
    asyncio.run(mixin._on_silence_nudge())
    assert len(mixin.sent) == 1
    event, payload = mixin.sent[0]
    assert event == "silence_nudge"
    assert payload["seq"] == NUDGE_PROBE_CAP + 1
    assert "打字" in payload["content"]
    assert mixin.ctx.silence_capped is True
    # Second wake stays quiet.
    mixin.sent.clear()
    asyncio.run(mixin._on_silence_nudge())
    assert mixin.sent == []
