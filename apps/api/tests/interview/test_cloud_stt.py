"""Regression coverage for cloud STT and best-result selection."""

from __future__ import annotations

from realmock.platform.capabilities.voice.stt import SttCredentials, SttResult
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from realmock.domains.interview.realtime import ws_handler
from realmock.domains.interview.realtime.voice.pipeline import _pick_stt_text
from realmock.domains.interview.realtime.core.events import TurnState
from realmock.platform.capabilities.voice.stt.cloud import is_local_stt_model, resolve_cloud_stt_model


def test_resolve_cloud_model_maps_local_sizes():
    assert resolve_cloud_stt_model("base") == "whisper-1"
    assert resolve_cloud_stt_model("small") == "whisper-1"
    assert resolve_cloud_stt_model("whisper-1") == "whisper-1"
    assert resolve_cloud_stt_model("gpt-4o-mini-transcribe") == "gpt-4o-mini-transcribe"
    assert is_local_stt_model("base")
    assert not is_local_stt_model("whisper-1")


def test_pick_stt_prefers_asr_over_browser_chinese():
    # The browser mishears “restaurant,” while the cloud correctly recognizes “interviewer”
    got = _pick_stt_text(
        "Hello, everything in the restaurant is audible",
        "Hello, both you and the interviewer can hear this",
    )
    assert "interviewer" in got.lower()
    assert "restaurant" not in got.lower()


def test_pick_stt_prefers_whisper_on_english():
    got = _pick_stt_text("Ah ah ah ah", "I used React and Docker")
    assert "React" in got


def _make_handler() -> ws_handler.InterviewWSHandler:
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock()
    h = ws_handler.InterviewWSHandler(ws, session_id=1)
    h.ctx.llm = MagicMock()
    h.ctx.llm.api_base = "https://api.openai.com/v1"
    h.ctx.llm.api_key = "sk-test"

    h.ctx.stt_creds = SttCredentials(
        provider="openai_compat",
        api_base="https://api.openai.com/v1",
        api_key="sk-stt-only",
        model="whisper-1",
    )
    h.ctx.whisper_model = "whisper-1"
    return h


class TestCloudSttPath:
    @pytest.mark.asyncio
    async def test_user_turn_uses_cloud_asr(self) -> None:
        h = _make_handler()
        h.ctx.turn_state = TurnState.USER_SPEAKING
        h.ctx.agent = None
        h._process_user_text = AsyncMock()
        with patch(
            "realmock.domains.interview.realtime.turn.stt_finish.transcribe_utterance_result",
            new_callable=AsyncMock,
            return_value=SttResult(text="Hello, both you and the interviewer can hear this", provider="local"),
        ) as mock_tr:
            await h._on_user_turn_end(
                {
                    "text": "Hello, everything in the restaurant is audible",
                    "pcm": "AAAA",
                    "sample_rate": 16000,
                },
                db=MagicMock(),
                session=MagicMock(),
            )
            mock_tr.assert_awaited()
            # Independent creds must be provided; do not silently use the reasoning Key
            kwargs = mock_tr.await_args.kwargs
            assert kwargs.get("creds") is h.ctx.stt_creds
            assert h.ctx.stt_creds.api_key == "sk-stt-only"
            assert h.ctx.stt_creds.api_key != h.ctx.llm.api_key
            args = h._process_user_text.await_args
            assert args.args[0] == "Hello, both you and the interviewer can hear this"

    @pytest.mark.asyncio
    async def test_transcribe_utterance_cloud_first(self) -> None:
        from realmock.platform.capabilities.voice.stt import transcribe_utterance

        with (
            patch(
                "realmock.platform.capabilities.voice.stt.openai_compat.transcribe_pcm_cloud",
                new_callable=AsyncMock,
                return_value="Cloud result is correct",
            ) as cloud,
            patch(
                "realmock.platform.capabilities.voice.stt.local.transcribe_pcm_base64_async",
                new_callable=AsyncMock,
                return_value="Local",
            ) as local,
        ):
            text = await transcribe_utterance(
                "AAAA",
                creds=SttCredentials(
                    provider="openai_compat",
                    api_base="https://api.openai.com/v1",
                    api_key="sk-x",
                    model="whisper-1",
                ),
            )
            assert text == "Cloud result is correct"
            cloud.assert_awaited()
            local.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_transcribe_falls_back_local(self) -> None:
        from realmock.platform.capabilities.voice.stt import transcribe_utterance

        with (
            patch(
                "realmock.platform.capabilities.voice.stt.openai_compat.transcribe_pcm_cloud",
                new_callable=AsyncMock,
                return_value="",
            ),
            patch(
                "realmock.platform.capabilities.voice.stt.local.transcribe_pcm_base64_async",
                new_callable=AsyncMock,
                return_value="Local fallback",
            ) as local,
        ):
            text = await transcribe_utterance(
                "AAAA",
                creds=SttCredentials(
                    provider="openai_compat",
                    api_base="https://api.openai.com/v1",
                    api_key="sk-x",
                    model="whisper-1",
                ),
            )
            assert text == "Local fallback"
            local.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_llm_key_without_asr_creds_goes_local(self) -> None:
        """Do not use the reasoning Key when no separate ASR is configured; legacy parameters with no Key in creds → local."""
        from realmock.platform.capabilities.voice.stt import transcribe_utterance

        with patch(
            "realmock.platform.capabilities.voice.stt.transcribe_local_async",
            new_callable=AsyncMock,
            return_value="Local only",
        ) as local:
            text = await transcribe_utterance("AAAA", model="base")
            assert text == "Local only"
            local.assert_awaited()
