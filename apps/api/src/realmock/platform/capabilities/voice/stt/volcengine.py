"""High-speed version identification of recording files of Volcano Engine (Doubao)."""

from __future__ import annotations

import base64
import logging
import uuid

from realmock.platform.core.security import make_pinned_async_client
from realmock.platform.capabilities.voice.stt.base import SttCredentials
from realmock.platform.capabilities.voice.stt.whisper import pcm_base64_to_wav_bytes

logger = logging.getLogger(__name__)

_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"


class VolcengineProvider:
    async def transcribe(
        self, pcm_b64: str, *, sample_rate: int, creds: SttCredentials
    ) -> str:
        app_key = (creds.app_key or creds.app_id or "").strip()
        access_key = (creds.access_key or creds.api_key or "").strip()
        resource_id = (creds.resource_id or "volc.bigasr.auc_turbo").strip()
        if not (app_key and access_key):
            logger.warning("Beanbao ASR missing AppKey/AccessKey")
            return ""

        try:
            wav = pcm_base64_to_wav_bytes(pcm_b64, sample_rate)
            audio_b64 = base64.b64encode(wav).decode("ascii")
        except Exception as e:
            logger.warning("Beanbao ASR audio preparation failed: %s", e)
            return ""

        headers = {
            "X-Api-App-Key": app_key,
            "X-Api-Access-Key": access_key,
            "X-Api-Resource-Id": resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Api-Sequence": "-1",
            "Content-Type": "application/json",
        }
        body = {
            "user": {"uid": "mock-interview"},
            "audio": {
                "data": audio_b64,
                "format": "wav",
                "rate": sample_rate,
                "bits": 16,
                "channel": 1,
            },
            "request": {
                "model_name": creds.model or "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
            },
        }
        try:
            async with make_pinned_async_client(_URL, timeout=45.0) as client:
                resp = await client.post(_URL, headers=headers, json=body)
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            logger.error("Beanbag ASR failed: %s", e)
            return ""

        # Response form: result.text or audio_info + result
        result = payload.get("result") or payload.get("data") or {}
        if isinstance(result, dict):
            text = result.get("text") or ""
            if not text:
                utterances = result.get("utterances") or []
                text = "".join(
                    (u.get("text") or "") for u in utterances if isinstance(u, dict)
                )
            return str(text).strip()
        if isinstance(result, str):
            return result.strip()
        logger.warning("Doubao ASR cannot parse response keys=%s", list(payload.keys())[:8])
        return ""
