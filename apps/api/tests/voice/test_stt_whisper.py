"""Whisper STT tests for src/realmock/platform/capabilities/voice/stt/whisper.py.

Covers: pcm_base64_to_wav_bytes shape/error branches, _get_model success/import/
ctor branches, transcribe_pcm_base64 no-model/short/success/lang-prob/short-text/
exception branches, warmup success/failure, transcribe_pcm_base64_async delegation
(model faked, no download).
Conventions: no real network/model downloads (all clients mocked).
"""

from __future__ import annotations

import base64
import io
import sys
import types
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from realmock.platform.capabilities.voice.stt import whisper as whisper_mod
from realmock.platform.capabilities.voice.stt.whisper import (
    pcm_base64_to_wav_bytes,
    transcribe_pcm_base64,
    transcribe_pcm_base64_async,
    warmup_whisper,
)


PCM = base64.b64encode(b"\x00\x01" * 500).decode("ascii")
LONG_PCM = base64.b64encode(b"\x00\x01" * 6000).decode("ascii")
SHORT_PCM = base64.b64encode(b"\x00\x01" * 100).decode("ascii")

def _fake_model(texts=("hello world",), lang_prob=0.9, exc=None):
    m = MagicMock()
    if exc is not None:
        m.transcribe.side_effect = exc
    else:
        segs = [SimpleNamespace(text=t) for t in texts]
        m.transcribe.return_value = (segs, SimpleNamespace(language_probability=lang_prob))
    return m


def test_pcm_to_wav_bytes():
    wav = pcm_base64_to_wav_bytes(PCM, 16000)
    assert wav[:4] == b"RIFF"
    with wave.open(io.BytesIO(wav), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
    with pytest.raises(Exception):
        pcm_base64_to_wav_bytes("a", 16000)


def test_get_model_success(monkeypatch):
    whisper_mod._get_model.cache_clear()
    fake_cls = MagicMock(return_value=object())
    fake_mod = types.ModuleType("faster_whisper")
    fake_mod.WhisperModel = fake_cls
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_mod)
    try:
        m = whisper_mod._get_model("base")
        assert m is not None
        fake_cls.assert_called_once_with("base", device="cpu", compute_type="int8")
    finally:
        whisper_mod._get_model.cache_clear()


def test_get_model_failure_import():
    whisper_mod._get_model.cache_clear()
    try:
        with patch.dict(sys.modules, {"faster_whisper": None}):
            assert whisper_mod._get_model("base") is None
    finally:
        whisper_mod._get_model.cache_clear()


def test_get_model_failure_ctor(monkeypatch):
    whisper_mod._get_model.cache_clear()
    fake_mod = types.ModuleType("faster_whisper")

    def _boom(*a, **k):
        raise RuntimeError("no model")

    fake_mod.WhisperModel = _boom
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_mod)
    try:
        assert whisper_mod._get_model("base") is None
    finally:
        whisper_mod._get_model.cache_clear()


def test_transcribe_no_model():
    with patch.object(whisper_mod, "_get_model", return_value=None):
        assert transcribe_pcm_base64(LONG_PCM) == ""


def test_transcribe_short_audio_skipped():
    fake = _fake_model()
    with patch.object(whisper_mod, "_get_model", return_value=fake):
        assert transcribe_pcm_base64(SHORT_PCM) == ""
        fake.transcribe.assert_not_called()


def test_transcribe_success():
    fake = _fake_model(texts=("hello ", "world"))
    with patch.object(whisper_mod, "_get_model", return_value=fake):
        assert transcribe_pcm_base64(LONG_PCM) == "hello world"
        _, kwargs = fake.transcribe.call_args
        assert kwargs["language"] is None
        assert kwargs["vad_filter"] is True


def test_transcribe_low_lang_prob_filtered():
    fake = _fake_model(texts=("hello",), lang_prob=0.1)
    with patch.object(whisper_mod, "_get_model", return_value=fake):
        assert transcribe_pcm_base64(LONG_PCM) == ""


def test_transcribe_lang_prob_read_failure():
    class _BadInfo:
        @property
        def language_probability(self):
            raise RuntimeError("no prob")

    m = MagicMock()
    m.transcribe.return_value = ([SimpleNamespace(text="hello")], _BadInfo())
    with patch.object(whisper_mod, "_get_model", return_value=m):
        assert transcribe_pcm_base64(LONG_PCM) == "hello"


def test_transcribe_short_text_filtered():
    fake = _fake_model(texts=("a",), lang_prob=0.9)
    with patch.object(whisper_mod, "_get_model", return_value=fake):
        assert transcribe_pcm_base64(LONG_PCM) == ""


def test_transcribe_exception_returns_empty():
    fake = _fake_model(exc=RuntimeError("decode"))
    with patch.object(whisper_mod, "_get_model", return_value=fake):
        assert transcribe_pcm_base64(LONG_PCM) == ""


@pytest.mark.asyncio
async def test_warmup_success_and_failure(monkeypatch):
    with patch.object(whisper_mod, "_get_model", return_value=object()):
        await warmup_whisper("base")
    with patch("asyncio.to_thread", new=AsyncMock(side_effect=RuntimeError("t"))):
        await warmup_whisper("base")


@pytest.mark.asyncio
async def test_transcribe_async_patches_thread():
    # Spec: whisper local model must be patched, never download a real model.
    with patch.object(whisper_mod, "transcribe_pcm_base64", return_value="async-text") as m:
        out = await transcribe_pcm_base64_async("AAA", sample_rate=16000, model_size="tiny")
    assert out == "async-text"
    assert m.called
