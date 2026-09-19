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
        last_tts_sent_at=now,
        speech_end_at=now - 100.0,
        mic_opened_at=now - 100.0,
        nudge_grace_sec=5.0,
        nudge_cooldown_sec=10.0,
        last_wait_seconds=0.0,
        last_nudge_at=0.0,
        silence_probe_question="",
        silence_probe_seq=0,
        silence_probe_msg_count=1,  # one assistant message in ctx.agent.messages
        silence_capped=False,
        last_silence_probe="",
        answer_started_at=0.0,
        closing=False,
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
    # The real method is synchronous (raises generation, clears event).
    mixin._begin_playback_wait = lambda: None  # type: ignore[method-assign]
    mixin._load_session = lambda db: None  # type: ignore[method-assign]
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


def test_stale_playback_report_releases_nudge():
    """A lost client tts_playback_done must not silence nudges forever."""
    mixin = _mixin(
        tts_sent_this_turn=True,
        playback_done=SimpleNamespace(is_set=lambda: False),
        last_tts_sent_at=_now() - 200.0,  # far past NUDGE_PLAYBACK_STALE_SEC
        silence_probe_question="Q?",
        silence_probe_seq=2,  # closing-nudge path (no probe LLM needed)
    )
    asyncio.run(mixin._on_silence_nudge())
    assert [e for e, _ in mixin.sent] == ["silence_nudge"]
    assert mixin.ctx.silence_capped is True


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


def test_probe_skipped_when_candidate_starts_answering_during_generation():
    """Candidate starts answering while the probe LLM call runs: the probe
    must never be spoken over their answer."""
    probe_calls: list[int] = []

    async def fake_probe(*, question, probe_hint, attempt, silent_sec):
        probe_calls.append(attempt)
        # Simulate the candidate typing / STT partial arriving mid-generation.
        mixin.ctx.answer_started_at = 1234.0
        return "probe-1"

    mixin = _mixin(
        silence_probe_question="Q?",
        silence_probe_seq=0,
        last_nudge_at=0.0,
    )
    mixin._generate_silence_probe = fake_probe  # type: ignore[method-assign]
    mixin._load_session = lambda db: SimpleNamespace(  # type: ignore[method-assign]
        personality="professional",
        strictness=3,
        current_phase=SimpleNamespace(id="tech", name="Tech"),
    )

    asyncio.run(mixin._on_silence_nudge())

    assert probe_calls == [1]  # generation ran...
    assert mixin.sent == []  # ...but nothing was spoken
    assert mixin.ctx.turn_state == TurnState.USER_SPEAKING


def test_probe_append_does_not_reset_cap_budget():
    """Probes merged into the same assistant message must not look like a new question."""
    probe_seq: list[int] = []

    async def fake_probe(*, question, probe_hint, attempt, silent_sec):
        probe_seq.append(attempt)
        return f"probe-{attempt}"

    mixin = _mixin(
        silence_probe_question="Q?",
        silence_probe_seq=0,
        last_nudge_at=0.0,
    )
    mixin._generate_silence_probe = fake_probe  # type: ignore[method-assign]
    mixin._load_session = lambda db: SimpleNamespace(  # type: ignore[method-assign]
        personality="professional",
        strictness=3,
        current_phase=SimpleNamespace(id="tech", name="Tech"),
    )

    # First probe: seq becomes 1 and the probe text is appended to history.
    asyncio.run(mixin._on_silence_nudge())
    assert len([e for e, _ in mixin.sent]) == 1
    assert probe_seq == [1]
    assert "\nprobe-1" in mixin.ctx.agent.messages[-1]["content"]

    # Cooldown has elapsed; the appended probe must not be mistaken for a new question.
    mixin.sent.clear()
    mixin.ctx.turn_state = TurnState.USER_SPEAKING
    mixin.ctx.last_nudge_at = 0.0
    asyncio.run(mixin._on_silence_nudge())
    assert probe_seq == [1, 2]
    assert mixin.ctx.silence_probe_seq == 2

    # Third wake: cap fires, closing nudge is spoken, no more probes generated.
    mixin.sent.clear()
    mixin.ctx.turn_state = TurnState.USER_SPEAKING
    mixin.ctx.last_nudge_at = 0.0
    asyncio.run(mixin._on_silence_nudge())
    assert probe_seq == [1, 2]
    assert len(mixin.sent) == 1
    assert mixin.ctx.silence_capped is True


def test_new_assistant_message_opens_a_new_probe_window():
    """A new question opens a fresh budget even when its text extends the old one.

    Regression: the old window key was the assistant text, so a rephrased
    question beginning with the previous one inherited the capped state and
    went permanently silent.
    """
    probe_seq: list[int] = []

    async def fake_probe(*, question, probe_hint, attempt, silent_sec):
        probe_seq.append(attempt)
        return f"probe-{attempt}"

    mixin = _mixin(
        silence_probe_question="Q?",
        silence_probe_seq=2,  # previous question already capped
        silence_capped=True,
        last_nudge_at=0.0,
    )
    mixin._generate_silence_probe = fake_probe  # type: ignore[method-assign]
    mixin._load_session = lambda db: SimpleNamespace(  # type: ignore[method-assign]
        personality="professional",
        strictness=3,
        current_phase=SimpleNamespace(id="tech", name="Tech"),
    )
    # The interviewer asks a new question whose text extends the old one.
    mixin.ctx.agent.messages.append(
        {"role": "assistant", "content": "Q? Specifically the cache layer."}
    )

    asyncio.run(mixin._on_silence_nudge())

    assert probe_seq == [1]  # fresh window, first probe again
    assert mixin.ctx.silence_capped is False
    assert mixin.ctx.silence_probe_question.startswith("Q? Specifically")
    assert "\nprobe-1" in mixin.ctx.agent.messages[-1]["content"]

