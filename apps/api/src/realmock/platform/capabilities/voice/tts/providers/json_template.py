"""Generic descriptor-driven TTS transport for vendors without a dedicated adapter.

The descriptor lives in the model entry's extras under ``tts_adapter`` and is authored
by the user against the vendor's own API docs:

```json
{
  "method": "POST",
  "url": "https://vendor.example/v1/tts",
  "headers": {"Authorization": "Bearer {{api_key}}"},
  "body": {"model": "{{model}}", "text": "{{text}}", "voice": "main"},
  "audio_path": "data.audio",
  "audio_encoding": "hex"
}
```

- ``{{api_key}}`` / ``{{model}}`` / ``{{text}}`` / ``{{voice}}`` placeholders are
  substituted everywhere in headers and body.
- ``audio_path`` is the dotted path to the audio payload; ``audio_encoding`` is
  ``hex`` (default) or ``base64``.
"""

from __future__ import annotations

import base64
import json
import logging

import httpx

from realmock.platform.config import get_settings
from realmock.platform.core.security import make_pinned_async_client
from realmock.platform.vendors.templates import fill_placeholders, get_dotted

logger = logging.getLogger(__name__)


def resolve_tts_adapter(creds) -> dict | None:
    """Return the user-authored ``tts_adapter`` descriptor, or None.

    Takes the credentials object loosely (duck-typed) so both the runtime TtsCredentials
    and test-page credentials work.
    """
    adapter = (getattr(creds, "extra", None) or {}).get("tts_adapter")
    if isinstance(adapter, dict) and str(adapter.get("url") or "").strip():
        return adapter
    return None


async def synthesize_json_template_to_base64(text: str, *, creds) -> str:
    """Turn a user-authored request template into an actual synthesis request."""
    adapter = resolve_tts_adapter(creds)
    if adapter is None:
        return ""
    key = (creds.api_key or "").strip()
    clean = (text or "").strip()
    if not key or not clean:
        return ""

    variables = {
        "api_key": key,
        "model": (creds.model or "").strip(),
        "voice": (creds.voice or "").strip(),
        "text": clean,
    }
    url = str(fill_placeholders(adapter.get("url"), variables)).strip()
    method = str(adapter.get("method") or "POST").upper()
    headers = fill_placeholders(adapter.get("headers") or {}, variables)
    headers.setdefault("Authorization", f"Bearer {key}")
    headers.setdefault("Content-Type", "application/json")
    body = fill_placeholders(adapter.get("body") or {}, variables)
    audio_path = str(adapter.get("audio_path") or "data.audio")
    encoding = str(adapter.get("audio_encoding") or "hex").lower()

    settings = get_settings()
    try:
        async with make_pinned_async_client(
            url,
            allow_local=settings.allow_local_llm,
            require_https=bool(settings.is_prod),
            timeout=60.0,
        ) as client:
            resp = await client.request(
                method, url, headers=headers, content=json.dumps(body, ensure_ascii=False)
            )
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as e:
        body_txt = ""
        try:
            body_txt = (e.response.text or "")[:200]
        except Exception:
            logger.debug("Failed to read template TTS error body", exc_info=True)
        logger.error("Template TTS HTTP %s: %s", e.response.status_code, body_txt)
        return ""
    except Exception as e:
        logger.error("Template TTS failed: %s", e)
        return ""

    audio = get_dotted(payload, audio_path)
    if not (isinstance(audio, str) and audio):
        logger.warning("Template TTS response has no audio at %s", audio_path)
        return ""
    try:
        raw = bytes.fromhex(audio) if encoding == "hex" else base64.b64decode(audio)
        return base64.b64encode(raw).decode("ascii")
    except ValueError:
        logger.error("Template TTS audio is neither hex nor base64")
        return ""
