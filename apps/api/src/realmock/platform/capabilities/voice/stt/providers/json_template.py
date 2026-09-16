"""Generic descriptor-driven STT transport for vendors without a dedicated adapter.

The descriptor lives in the model entry's extras under ``stt_adapter`` and is authored by
the user against the vendor's own API docs:

```json
{
  "method": "POST",
  "url": "https://vendor.example/v1/asr",
  "headers": {"Authorization": "Bearer {{api_key}}"},
  "fields": {"model": "{{model}}"},
  "json_body": null,
  "multipart": {"file_field": "file", "filename": "audio.wav", "content_type": "audio/wav"},
  "text_path": "text"
}
```

- ``{{api_key}}`` / ``{{model}}`` placeholders are substituted everywhere.
- When ``json_body`` is set it is sent as JSON (audio goes where ``{{audio_base64}}``
  appears); otherwise ``fields`` + the wav ``multipart`` file are sent as form data.
- ``text_path`` is the dotted path to the transcript in the response.
"""

from __future__ import annotations

import base64
import json
import logging

import httpx

from realmock.platform.config import get_settings
from realmock.platform.core.security import make_pinned_async_client
from realmock.platform.capabilities.voice.stt.base import SttCredentials
from realmock.platform.capabilities.voice.stt.providers.whisper import pcm_base64_to_wav_bytes
from realmock.platform.vendors.templates import fill_placeholders, get_dotted

logger = logging.getLogger(__name__)

_MULTIPART_DEFAULTS = {"file_field": "file", "filename": "audio.wav", "content_type": "audio/wav"}


def resolve_stt_adapter(creds: SttCredentials) -> dict | None:
    """Return the user-authored ``stt_adapter`` descriptor, or None."""
    adapter = (creds.extra or {}).get("stt_adapter")
    if isinstance(adapter, dict) and str(adapter.get("url") or "").strip():
        return adapter
    return None


class JsonTemplateSttProvider:
    """Turns a user-authored request template into an actual transcription request."""

    async def transcribe(
        self, pcm_b64: str, *, sample_rate: int, creds: SttCredentials
    ) -> str:
        adapter = resolve_stt_adapter(creds)
        if adapter is None:
            return ""
        key = (creds.api_key or "").strip()
        if not key:
            return ""
        try:
            raw_len = len(base64.b64decode(pcm_b64))
        except Exception:
            return ""
        if raw_len < sample_rate * 2 * 0.35:
            return ""
        try:
            wav_bytes = pcm_base64_to_wav_bytes(pcm_b64, sample_rate)
        except Exception as e:
            logger.warning("PCM→WAV failed: %s", e)
            return ""

        variables = {"api_key": key, "model": (creds.model or "").strip()}
        url = str(fill_placeholders(adapter.get("url"), variables)).strip()
        method = str(adapter.get("method") or "POST").upper()
        headers = fill_placeholders(adapter.get("headers") or {}, variables)
        headers.setdefault("Authorization", f"Bearer {key}")
        text_path = str(adapter.get("text_path") or "text")

        json_body = adapter.get("json_body")
        if json_body is not None:
            body = fill_placeholders(json_body, variables)
            body = fill_placeholders(body, {"audio_base64": base64.b64encode(wav_bytes).decode("ascii")})
            headers.setdefault("Content-Type", "application/json")
            data = None
            files = None
            content = json.dumps(body, ensure_ascii=False).encode("utf-8")
        else:
            content = None
            data = fill_placeholders(adapter.get("fields") or {}, variables)
            multipart = {**_MULTIPART_DEFAULTS, **(adapter.get("multipart") or {})}
            files = {
                str(multipart["file_field"]): (
                    str(multipart["filename"]),
                    wav_bytes,
                    str(multipart["content_type"]),
                )
            }

        settings = get_settings()
        try:
            async with make_pinned_async_client(
                url,
                allow_local=settings.allow_local_llm,
                require_https=bool(settings.is_prod),
                timeout=30.0,
            ) as client:
                if content is not None:
                    resp = await client.post(url, headers=headers, content=content)
                else:
                    resp = await client.request(method, url, headers=headers, data=data, files=files)
                resp.raise_for_status()
                payload = resp.json()
        except httpx.HTTPStatusError as e:
            body_txt = ""
            try:
                body_txt = (e.response.text or "")[:200]
            except Exception:
                logger.debug("Failed to read template STT error body", exc_info=True)
            logger.error("Template STT HTTP %s: %s", e.response.status_code, body_txt)
            return ""
        except Exception as e:
            logger.error("Template STT failed: %s", e)
            return ""

        if isinstance(payload, str):
            return payload.strip()
        text = str(get_dotted(payload, text_path) or "").strip()
        return text
