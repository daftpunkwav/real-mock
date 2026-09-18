"""TTS queue credential-preservation tests.

Regression guard: the worker used to rebuild TtsCredentials field-by-field when
overlaying the per-emotion voice, silently dropping newer credential fields
(full_url / extra request overrides). dataclasses.replace() must be used so a
full-URL MiniMax provider keeps posting to its verbatim endpoint with its
request overrides intact. Conventions: synthesize_speech faked, no network.
"""

from __future__ import annotations

import asyncio

from realmock.domains.interview.realtime.voice.tts_queue import _SentenceTTSQueue
from realmock.platform.capabilities.voice.tts import TtsCredentials
from realmock.platform.capabilities.voice.tts.voice_resolve import VoiceProsody


def test_worker_preserves_full_url_and_extra_when_overlaying_voice() -> None:
    """Per-emotion voice overlay must not drop full_url / protocol / extra."""

    async def _scenario():
        captured: list[TtsCredentials] = []

        async def _fake_synth(sentence, *, creds=None, rate="+0%", pitch="+0Hz", emotion="neutral"):
            captured.append(creds)
            return f"audio:{sentence}"

        import realmock.domains.interview.realtime.voice.tts_queue as q_mod

        orig = q_mod.synthesize_speech
        q_mod.synthesize_speech = _fake_synth
        try:
            q = _SentenceTTSQueue()
            q.set_prosody(VoiceProsody(voice="base-voice"))
            q.set_tts_creds(
                TtsCredentials(
                    handler="minimax_speech",
                    api_base="https://api.minimaxi.com/v1/t2a_v2",
                    full_url=True,
                    protocol="openai_chat",
                    extra={"tts_request": {"language_boost": "auto"}},
                    voice="female-shaonv",
                )
            )
            sent: list[tuple[str, str]] = []

            async def send_cb(msg_type, **payload):
                sent.append((payload["sentence"], payload["data"]))

            await q.start(send_cb)
            await q.enqueue("Hello.")
            await q.flush_remainder("")
            await q.stop()
        finally:
            q_mod.synthesize_speech = orig

        assert sent == [("Hello.", "audio:Hello.")]
        assert len(captured) == 1
        creds = captured[0]
        # Fields a manual rebuild used to lose:
        assert creds.full_url is True
        assert creds.extra == {"tts_request": {"language_boost": "auto"}}
        assert creds.protocol == "openai_chat"
        # Only the voice moved (emotion overlay keeps the base voice here).
        assert creds.voice == "base-voice"

    asyncio.run(_scenario())
