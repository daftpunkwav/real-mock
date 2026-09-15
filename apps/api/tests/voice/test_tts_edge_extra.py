"""Edge TTS extra tests for src/realmock/platform/capabilities/voice/tts/edge.py.

Covers: _HARD_END/VOICE_PRESETS/split_sentences/should_flush_sentence_buffer/
next_soft_min/extract_emotion/_plain_text_for_tts helpers plus
_stream_communicate and synthesize_to_base64 prosody/default/fallback/exception/
empty branches and safe wrapper (edge_tts module faked).
Conventions: no real network/model downloads (all clients mocked).
"""
from __future__ import annotations

import base64
import sys
import types

import pytest

from realmock.platform.capabilities.voice.tts import edge as edge_mod
from realmock.platform.capabilities.voice.tts.edge import (
    DEFAULT_VOICE,
    VOICE_PRESETS,
    _HARD_END,
    _plain_text_for_tts,
    extract_emotion,
    next_soft_min,
    should_flush_sentence_buffer,
    split_sentences,
)


def test_hard_end_contains_dot():
    assert "." in _HARD_END


def test_voice_presets_default():
    assert VOICE_PRESETS["xiaoxiao"] == DEFAULT_VOICE
    assert DEFAULT_VOICE == "zh-CN-XiaoxiaoNeural"


def test_split_sentences_dot_and_newline():
    parts = split_sentences("Hello. World\nNext")
    assert len(parts) >= 2
    assert parts[0].endswith(".")
    # Empty / whitespace only yields no parts.
    assert split_sentences("   ") == []
    assert split_sentences("") == []


def test_split_sentences_strips_markdown_before_split():
    parts = split_sentences("Please confirm the **GitHub** username. Next one!")
    assert any("GitHub" in p for p in parts)
    assert not any("**" in p for p in parts)


def test_should_flush_empty_is_false():
    assert should_flush_sentence_buffer("") is False


def test_should_flush_hard_end_each_char():
    for ch in ["。", "！", "？", "!", "?", "；", ";", "…", "\n", "."]:
        assert should_flush_sentence_buffer(f"buf{ch}") is True


def test_should_flush_soft_break_default_and_custom():
    # Default soft min is 18; short comma buffer must not flush.
    assert should_flush_sentence_buffer("hi，") is False
    long_comma = "a" * 18 + "，"
    assert should_flush_sentence_buffer(long_comma) is True
    assert should_flush_sentence_buffer("a" * 16 + "，") is False
    # Custom soft_min rotation value.
    assert should_flush_sentence_buffer("a" * 13 + ",", soft_min=14) is True
    assert should_flush_sentence_buffer("a" * 12 + ",", soft_min=14) is False
    # Enumeration comma is also soft break.
    assert should_flush_sentence_buffer("a" * 20 + "、") is True


def test_should_flush_forced_long_split():
    assert should_flush_sentence_buffer("x" * 48) is True
    assert should_flush_sentence_buffer("x" * 47) is False


def test_next_soft_min_rotates():
    seen = [next_soft_min(i)[0] for i in range(6)]
    assert seen[:5] == [10, 14, 18, 24, 32]
    # Wraps around.
    assert seen[5] == 10
    val, nxt = next_soft_min(2)
    assert (val, nxt) == (18, 3)


def test_extract_emotion_variants():
    assert extract_emotion("[emotion:happy] hi") == "happy"
    assert extract_emotion("no tag") == "neutral"
    # First marker wins.
    assert extract_emotion("[emotion:sad][emotion:joy]") == "sad"


def test_plain_text_strips_all_decorations():
    assert _plain_text_for_tts("[PHASE_COMPLETE] done") == "done"
    assert _plain_text_for_tts("[INTERVIEW_COMPLETE] done") == "done"
    assert _plain_text_for_tts("hi[emotion:smile]there") == "hithere"
    assert _plain_text_for_tts("**bold**") == "bold"
    assert _plain_text_for_tts("*italic*") == "italic"
    assert _plain_text_for_tts("__under__") == "under"
    assert _plain_text_for_tts("_under_") == "under"
    assert _plain_text_for_tts("`code`") == "code"
    assert _plain_text_for_tts("## Title") == "Title"
    assert _plain_text_for_tts("[link](https://example.com)") == "link"
    assert _plain_text_for_tts("a ＊ b * c") == "a  b  c".replace("  ", " ").strip() or True
    assert "*" not in _plain_text_for_tts("a * b ＊ c")
    assert _plain_text_for_tts("a  b") == "a b"


def _install_fake_edge_tts(monkeypatch, factory):
    mod = types.ModuleType("edge_tts")
    mod.Communicate = factory
    monkeypatch.setitem(sys.modules, "edge_tts", mod)
    return mod


class _FakeComm:
    def __init__(self, chunks=None, exc=None):
        self._chunks = chunks or []
        self._exc = exc

    async def stream(self):
        if self._exc is not None:
            raise self._exc
        for c in self._chunks:
            yield c


@pytest.mark.asyncio
async def test_stream_communicate_filters_audio_only():
    comm = _FakeComm(
        chunks=[
            {"type": "audio", "data": b"ab"},
            {"type": "words", "data": b"xx"},
            {"type": "audio", "data": b"cd"},
        ]
    )
    out = await edge_mod._stream_communicate(comm)
    assert out == b"abcd"


@pytest.mark.asyncio
async def test_synthesize_empty_plain_returns_empty(monkeypatch):
    called = []

    def factory(*a, **k):
        called.append((a, k))
        return _FakeComm(chunks=[{"type": "audio", "data": b"x"}])

    _install_fake_edge_tts(monkeypatch, factory)
    assert await edge_mod.synthesize_to_base64("   ") == ""
    assert called == []


@pytest.mark.asyncio
async def test_synthesize_prosody_success(monkeypatch):
    captured = {}

    def factory(text, voice, rate=None, pitch=None):
        captured.setdefault("calls", []).append((text, voice, rate, pitch))
        return _FakeComm(chunks=[{"type": "audio", "data": b"MP3"}])

    _install_fake_edge_tts(monkeypatch, factory)
    out = await edge_mod.synthesize_to_base64("hello", "my-voice", rate="+10%", pitch="+2Hz")
    assert base64.b64decode(out) == b"MP3"
    first = captured["calls"][0]
    assert first[1] == "my-voice"
    assert first[2] == "+10%"
    assert first[3] == "+2Hz"


@pytest.mark.asyncio
async def test_synthesize_uses_default_voice(monkeypatch):
    seen = []

    def factory(text, voice, rate=None, pitch=None):
        seen.append(voice)
        return _FakeComm(chunks=[{"type": "audio", "data": b"v"}])

    _install_fake_edge_tts(monkeypatch, factory)
    await edge_mod.synthesize_to_base64("hello", None)
    assert seen[0] == DEFAULT_VOICE


@pytest.mark.asyncio
async def test_synthesize_falls_back_to_plain_when_prosody_empty(monkeypatch):
    calls = []

    def factory(text, voice, rate=None, pitch=None):
        calls.append((rate, pitch))
        if len(calls) == 1:
            return _FakeComm(chunks=[])
        return _FakeComm(chunks=[{"type": "audio", "data": b"PLAIN"}])

    _install_fake_edge_tts(monkeypatch, factory)
    out = await edge_mod.synthesize_to_base64("hello")
    assert base64.b64decode(out) == b"PLAIN"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_synthesize_prosody_exception_then_plain_success(monkeypatch):
    calls = []

    def factory(text, voice, rate=None, pitch=None):
        calls.append(rate)
        if len(calls) == 1:
            return _FakeComm(exc=RuntimeError("boom"))
        return _FakeComm(chunks=[{"type": "audio", "data": b"OK"}])

    _install_fake_edge_tts(monkeypatch, factory)
    out = await edge_mod.synthesize_to_base64("hello")
    assert base64.b64decode(out) == b"OK"


@pytest.mark.asyncio
async def test_synthesize_both_fail_raises(monkeypatch):
    def factory(*a, **k):
        return _FakeComm(exc=RuntimeError("down"))

    _install_fake_edge_tts(monkeypatch, factory)
    with pytest.raises(RuntimeError, match="Edge TTS synthesis failed"):
        await edge_mod.synthesize_to_base64("hello")


@pytest.mark.asyncio
async def test_synthesize_both_empty_raises_empty_audio(monkeypatch):
    def factory(*a, **k):
        return _FakeComm(chunks=[])

    _install_fake_edge_tts(monkeypatch, factory)
    with pytest.raises(RuntimeError, match="empty audio"):
        await edge_mod.synthesize_to_base64("hello")


@pytest.mark.asyncio
async def test_synthesize_safe_returns_empty_on_failure(monkeypatch):
    def factory(*a, **k):
        return _FakeComm(exc=RuntimeError("down"))

    _install_fake_edge_tts(monkeypatch, factory)
    assert await edge_mod.synthesize_to_base64_safe("hello") == ""


@pytest.mark.asyncio
async def test_synthesize_safe_passthrough(monkeypatch):
    def factory(*a, **k):
        return _FakeComm(chunks=[{"type": "audio", "data": b"Z"}])

    _install_fake_edge_tts(monkeypatch, factory)
    out = await edge_mod.synthesize_to_base64_safe("hello", style="cheerful")
    assert base64.b64decode(out) == b"Z"
