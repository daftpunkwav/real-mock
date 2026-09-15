"""Local STT tests for src/realmock/platform/capabilities/voice/stt/local.py.

Covers: LocalWhisperProvider model-selection tiny/whisper-1 mapping branches
(transcribe mocked, no download).
Conventions: no real network/model downloads (all clients mocked).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from realmock.platform.capabilities.voice.stt import local as local_mod
from realmock.platform.capabilities.voice.stt.base import SttCredentials
from realmock.platform.capabilities.voice.stt.local import LocalWhisperProvider


@pytest.mark.asyncio
async def test_local_provider_model_selection():
    with patch.object(
        local_mod, "transcribe_pcm_base64_async", new=AsyncMock(return_value="local-ok")
    ) as m:
        p = LocalWhisperProvider()
        assert (
            await p.transcribe("AAA", sample_rate=16000, creds=SttCredentials(model="tiny"))
            == "local-ok"
        )
        assert m.await_args.kwargs["model_size"] == "tiny"
    with patch.object(
        local_mod, "transcribe_pcm_base64_async", new=AsyncMock(return_value="local-ok")
    ) as m2:
        p = LocalWhisperProvider()
        assert (
            await p.transcribe("AAA", sample_rate=16000, creds=SttCredentials(model="whisper-1"))
            == "local-ok"
        )
        assert m2.await_args.kwargs["model_size"] == "small"
