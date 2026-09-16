"""STT adapter public type."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class SttCredentials:
    """Identification credentials independent of "Interview Thinking"; silent fallback of MiniMax Chat Key is prohibited."""

    provider: str = "local"
    protocol: str = "openai_chat"
    api_base: str = ""
    # Full-URL providers: api_base is the verbatim endpoint and protocol path appending is skipped.
    full_url: bool = False
    api_key: str = ""
    model: str = ""
    app_id: str = ""
    api_secret: str = ""
    access_key: str = ""
    resource_id: str = ""
    app_key: str = ""
    fallback_handler: str = "local"
    fallback_mode: str = "transcribe"
    extra: dict = field(default_factory=dict)


class SttProvider(Protocol):
    async def transcribe(
        self, pcm_b64: str, *, sample_rate: int, creds: SttCredentials
    ) -> str: ...
