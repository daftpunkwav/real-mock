"""Stage-test tests for realmock.domains.settings.services.stage_tests.

Covers: transcript normalization, fixture fallback branches, and
  recognize/reason/speak execution paths.
Conventions: collaborators patched; no network, audio, or LLM calls.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import realmock.domains.settings.services.stage_tests as st
from realmock.domains.settings.services.stage_tests import (
    _normalize_zh,
    load_fixture,
)


class TestNormalizeMechanical:
    def test_lower_and_strip_non_word(self) -> None:
        # Mechanical lower + strip-non-word, not semantic translation.
        assert _normalize_zh("Up 50% year over year.") == "up50yearoveryear"
        assert _normalize_zh("  Hello, World! ") == "helloworld"
        assert _normalize_zh("") == ""

    def test_chinese_kept_digits_kept(self) -> None:
        assert _normalize_zh("增长 50%") == "增长50"
        assert _normalize_zh(None) == ""  # type: ignore[arg-type]


class TestLoadFixture:
    def test_missing_expected_uses_builtin_default(self, tmp_path, monkeypatch) -> None:
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"RIFF" + b"\x00" * 2000)
        monkeypatch.setattr(st, "_EXPECTED_PATH", tmp_path / "missing.json")
        monkeypatch.setattr(st, "_AUDIO_PATH", audio)
        data, expected = load_fixture()
        assert data[:4] == b"RIFF"
        assert expected == "An increase of 50% year-on-year"

    def test_corrupt_expected_uses_default(self, tmp_path, monkeypatch) -> None:
        bad = tmp_path / "expected.json"
        bad.write_text("{not json", encoding="utf-8")
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"RIFF" + b"\x00" * 2000)
        monkeypatch.setattr(st, "_EXPECTED_PATH", bad)
        monkeypatch.setattr(st, "_AUDIO_PATH", audio)
        _, expected = load_fixture()
        assert expected == "An increase of 50% year-on-year"

    def test_empty_expected_value_uses_default(self, tmp_path, monkeypatch) -> None:
        exp = tmp_path / "expected.json"
        exp.write_text("{}", encoding="utf-8")
        audio = tmp_path / "a.wav"
        audio.write_bytes(b"RIFF" + b"\x00" * 2000)
        monkeypatch.setattr(st, "_EXPECTED_PATH", exp)
        monkeypatch.setattr(st, "_AUDIO_PATH", audio)
        _, expected = load_fixture()
        assert expected == "An increase of 50% year-on-year"

    def test_missing_audio_raises(self, tmp_path, monkeypatch) -> None:
        exp = tmp_path / "expected.json"
        exp.write_text('{"expected_zh": "hi"}', encoding="utf-8")
        monkeypatch.setattr(st, "_EXPECTED_PATH", exp)
        monkeypatch.setattr(st, "_AUDIO_PATH", tmp_path / "nope.wav")
        with pytest.raises(FileNotFoundError):
            load_fixture()


def _cfg(**over):
    base = {
        "provider": "custom",
        "api_base": "http://x/v1",
        "api_key": "k",
        "protocol": "openai_chat",
        "model": "m",
        "extras": {},
        "fallback_handler": "local",
        "fallback_mode": "transcribe",
    }
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_recognize_coming_soon() -> None:
    db = MagicMock()
    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg(provider="zhipu_glm4_voice")),
        patch.object(st, "find_provider", return_value={"status": "coming_soon"}),
    ):
        out = await st.test_recognize(db)
    assert out["success"] is False
    assert "not wired" in out["message"]
    assert out["fallback"] == "local"


@pytest.mark.asyncio
async def test_recognize_missing_audio() -> None:
    db = MagicMock()
    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg()),
        patch.object(st, "find_provider", return_value=None),
        patch.object(st, "load_fixture", side_effect=FileNotFoundError("Missing standard test audio: x")),
    ):
        out = await st.test_recognize(db)
    assert out["success"] is False
    assert "Missing standard test audio" in out["message"]


@pytest.mark.asyncio
async def test_recognize_fallback_path() -> None:
    db = MagicMock()
    fake = SimpleNamespace(text="hello", fallback=True, provider="local")
    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg()),
        patch.object(st, "find_provider", return_value=None),
        patch.object(st, "load_fixture", return_value=(b"RIFF1234", "hello")),
        patch.object(st, "transcribe_utterance_result", new=AsyncMock(return_value=fake)),
    ):
        out = await st.test_recognize(db)
    assert out["success"] is False
    assert "fell back" in out["message"]
    assert out["fallback"] == "local"


@pytest.mark.asyncio
async def test_recognize_match_and_mismatch() -> None:
    db = MagicMock()
    good = SimpleNamespace(text="Up 50% year over year!", fallback=False, provider="custom")
    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg(model="mm")),
        patch.object(st, "find_provider", return_value=None),
        patch.object(st, "load_fixture", return_value=(b"RIFF1234", "Up 50% year over year.")),
        patch.object(st, "transcribe_utterance_result", new=AsyncMock(return_value=good)),
    ):
        out = await st.test_recognize(db)
    assert out["success"] is True
    assert "matched" in out["message"]
    assert out["model"] == "mm"

    bad = SimpleNamespace(text="totally different", fallback=False, provider="custom")
    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg()),
        patch.object(st, "find_provider", return_value=None),
        patch.object(st, "load_fixture", return_value=(b"RIFF1234", "Up 50% year over year.")),
        patch.object(st, "transcribe_utterance_result", new=AsyncMock(return_value=bad)),
    ):
        out2 = await st.test_recognize(db)
    assert out2["success"] is False
    assert "did not match" in out2["message"]

    empty = SimpleNamespace(text="", fallback=False, provider="custom")
    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg()),
        patch.object(st, "find_provider", return_value=None),
        patch.object(st, "load_fixture", return_value=(b"RIFF1234", "expected")),
        patch.object(st, "transcribe_utterance_result", new=AsyncMock(return_value=empty)),
    ):
        out3 = await st.test_recognize(db)
    assert out3["success"] is False


@pytest.mark.asyncio
async def test_reason_coming_soon() -> None:
    db = MagicMock()
    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg(provider="zhipu")),
        patch.object(st, "find_provider", return_value={"status": "coming_soon"}),
    ):
        out = await st.test_reason(db)
    assert out["success"] is False
    assert "not wired" in out["message"]


@pytest.mark.asyncio
async def test_reason_missing_key() -> None:
    db = MagicMock()
    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg(api_key="")),
        patch.object(st, "find_provider", return_value=None),
    ):
        out = await st.test_reason(db)
    assert out["success"] is False
    assert "API Key" in out["message"]


@pytest.mark.asyncio
async def test_reason_ok_with_reply_and_empty() -> None:
    db = MagicMock()
    llm = SimpleNamespace(model="m1", test_connection=AsyncMock(return_value=(True, "ok")), chat=AsyncMock(return_value="Hi there interviewer"))
    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg()),
        patch.object(st, "find_provider", return_value=None),
        patch.object(st.UnifiedLLMClient, "from_stage_config", return_value=llm),
    ):
        out = await st.test_reason(db)
    assert out["success"] is True
    assert "Reasoning OK" in out["message"]

    llm2 = SimpleNamespace(model="m1", test_connection=AsyncMock(return_value=(True, "ok")), chat=AsyncMock(return_value="   "))
    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg()),
        patch.object(st, "find_provider", return_value=None),
        patch.object(st.UnifiedLLMClient, "from_stage_config", return_value=llm2),
    ):
        out2 = await st.test_reason(db)
    assert out2["success"] is True
    assert out2["message"] == "ok"


@pytest.mark.asyncio
async def test_reason_fail_and_exception() -> None:
    db = MagicMock()
    llm = SimpleNamespace(model="m1", test_connection=AsyncMock(return_value=(False, "bad key")), chat=AsyncMock())
    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg()),
        patch.object(st, "find_provider", return_value=None),
        patch.object(st.UnifiedLLMClient, "from_stage_config", return_value=llm),
    ):
        out = await st.test_reason(db)
    assert out["success"] is False
    assert out["message"] == "bad key"

    bad = SimpleNamespace(model="m1", test_connection=AsyncMock(side_effect=RuntimeError("boom")), chat=AsyncMock())
    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg()),
        patch.object(st, "find_provider", return_value=None),
        patch.object(st.UnifiedLLMClient, "from_stage_config", return_value=bad),
    ):
        out2 = await st.test_reason(db)
    assert out2["success"] is False
    assert "Reasoning test failed" in out2["message"]


@pytest.mark.asyncio
async def test_speak_coming_soon_and_text_only() -> None:
    db = MagicMock()
    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg(provider="doubao_s2s")),
        patch.object(st, "find_provider", return_value={"status": "coming_soon"}),
    ):
        out = await st.test_speak(db)
    assert out["success"] is False
    assert "fall back" in out["message"]

    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg(provider="edge", extras={"speech_speak_mode": "text_only"})),
        patch.object(st, "find_provider", return_value=None),
    ):
        out2 = await st.test_speak(db)
    assert out2["success"] is True
    assert "captions-only" in out2["message"]

    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg(provider="none")),
        patch.object(st, "find_provider", return_value=None),
    ):
        out3 = await st.test_speak(db)
    assert out3["success"] is True


@pytest.mark.asyncio
async def test_speak_edge_ok_and_fail_and_custom() -> None:
    db = MagicMock()
    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg(provider="edge", model="")),
        patch.object(st, "find_provider", return_value=None),
        patch.object(st, "synthesize_speech", new=AsyncMock(return_value="QUJD")),
    ):
        out = await st.test_speak(db)
    assert out["success"] is True
    assert out["audio_base64"] == "QUJD"

    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg(provider="edge")),
        patch.object(st, "find_provider", return_value=None),
        patch.object(st, "synthesize_speech", new=AsyncMock(return_value="")),
    ):
        out2 = await st.test_speak(db)
    assert out2["success"] is False
    assert out2["fallback"] == "local"

    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg(provider="custom", model="mimo-v2.5-tts")),
        patch.object(st, "find_provider", return_value=None),
        patch.object(st, "synthesize_custom_speech", new=AsyncMock(return_value="QQ==")),
    ):
        out3 = await st.test_speak(db)
    assert out3["success"] is True

    with (
        patch.object(st, "get_stage_config_for_runtime", return_value=_cfg(provider="custom")),
        patch.object(st, "find_provider", return_value=None),
        patch.object(st, "synthesize_custom_speech", new=AsyncMock(return_value="")),
    ):
        out4 = await st.test_speak(db)
    assert out4["success"] is False
