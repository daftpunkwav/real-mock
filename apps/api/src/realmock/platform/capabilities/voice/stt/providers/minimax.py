"""MiniMax speech-to-text adapter: POST /v1/speech_to_text (multipart wav upload).

Request shape is driven by the vendor descriptor (``platform/vendors/defs/minimax.json``);
every field of the request (form fields and extra headers) can be overridden per model
entry via ``extras["stt_request"] = {"headers": {...}, "fields": {...}}`` (deep-merged).
The ``language`` hint header is intentionally absent by default so MiniMax's
mixed-language recognition stays enabled.
"""

from __future__ import annotations

import base64
import logging

import httpx

from realmock.platform.config import get_settings
from realmock.platform.core.security import make_pinned_async_client
from realmock.platform.capabilities.voice.stt.base import SttCredentials
from realmock.platform.capabilities.voice.stt.providers.cloud import is_local_stt_model
from realmock.platform.capabilities.voice.stt.providers.whisper import pcm_base64_to_wav_bytes
from realmock.platform.vendors import vendor_def
from realmock.platform.vendors.templates import deep_merge, get_dotted

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "asr-1.0"

# Built-in floor defaults, used only when the vendor descriptor fails to load.
_FALLBACK_FIELDS = {"model": DEFAULT_MODEL, "response_format": "json"}


def _capability_def() -> dict:
    capability = (vendor_def("minimax") or {}).get("capabilities", {}).get("recognize")
    return capability if isinstance(capability, dict) else {}


def _endpoint_path(fallback: str) -> str:
    """Descriptor-declared endpoint path (leading slash normalized), or ``fallback``."""
    path = str(_capability_def().get("endpoint_path") or fallback).strip()
    return path if path.startswith("/") else f"/{path}"


def build_stt_request(creds: SttCredentials) -> tuple[dict, dict]:
    """Resolve (headers, multipart fields): descriptor defaults ← credentials ← extras overrides.

    ``creds.model`` wins over the descriptor's model field (it is the explicit model-entry
    choice), EXCEPT local whisper size names: ``build_stt_credentials`` fills them in as a
    generic default ("base") when the entry has no model, and they are not MiniMax model
    ids — the descriptor default (asr-1.0) applies instead. Extras ``stt_request``
    overrides everything, so users can customize any request-body/header field from the
    settings page.
    """
    request_def = _capability_def().get("request") or {}
    headers = dict(request_def.get("headers") or {})
    fields = dict(request_def.get("fields") or _FALLBACK_FIELDS)
    model = (creds.model or "").strip()
    if model and not is_local_stt_model(model):
        fields["model"] = model
    override = (creds.extra or {}).get("stt_request")
    if isinstance(override, dict):
        headers = deep_merge(headers, override.get("headers"))
        fields = deep_merge(fields, override.get("fields"))
    return headers, fields


class MiniMaxSttProvider:
    """MiniMax ASR: multipart upload of a wav file; the response carries the transcript in ``text``."""

    async def transcribe(
        self, pcm_b64: str, *, sample_rate: int, creds: SttCredentials
    ) -> str:
        key = (creds.api_key or "").strip()
        base = (creds.api_base or "").strip().rstrip("/")
        if not key or not base:
            return ""
        try:
            raw_len = len(base64.b64decode(pcm_b64))
        except Exception:
            return ""
        # < ~0.35s int16 mono is too short to transcribe meaningfully
        if raw_len < sample_rate * 2 * 0.35:
            return ""
        try:
            wav_bytes = pcm_base64_to_wav_bytes(pcm_b64, sample_rate)
        except Exception as e:
            logger.warning("PCM→WAV failed: %s", e)
            return ""

        # Full-URL mode posts to api_base verbatim; otherwise the descriptor's documented
        # endpoint path is appended (literal fallback when the descriptor fails to load).
        url = base if creds.full_url else f"{base}{_endpoint_path('/speech_to_text')}"
        extra_headers, fields = build_stt_request(creds)
        headers = {"Authorization": f"Bearer {key}", **extra_headers}
        files = {"file": ("audio.wav", wav_bytes, "audio/wav")}

        settings = get_settings()
        try:
            async with make_pinned_async_client(
                url,
                allow_local=settings.allow_local_llm,
                require_https=bool(settings.is_prod),
                timeout=30.0,
            ) as client:
                resp = await client.post(url, headers=headers, data=fields, files=files)
                resp.raise_for_status()
                payload = resp.json()
        except httpx.HTTPStatusError as e:
            body = ""
            try:
                body = (e.response.text or "")[:200]
            except Exception:
                logger.debug("Failed to read MiniMax STT error response body", exc_info=True)
            logger.error("MiniMax STT HTTP %s: %s", e.response.status_code, body)
            return ""
        except Exception as e:
            logger.error("MiniMax STT failed: %s", e)
            return ""

        text_path = str(_capability_def().get("response", {}).get("text_path") or "text")
        text = str(get_dotted(payload, text_path) or "").strip()
        if len(text) < 2:
            return ""
        return text
