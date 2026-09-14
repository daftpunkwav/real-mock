"""Baidu short speech recognition."""

from __future__ import annotations

import base64
import logging

from realmock.platform.core.security import make_pinned_async_client
from realmock.platform.capabilities.voice.stt.base import SttCredentials
from realmock.platform.capabilities.voice.stt.whisper import pcm_base64_to_wav_bytes

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
_ASR_URL = "https://vop.baidu.com/server_api"


class BaiduProvider:
    async def transcribe(
        self, pcm_b64: str, *, sample_rate: int, creds: SttCredentials
    ) -> str:
        api_key = (creds.api_key or "").strip()
        secret = (creds.api_secret or "").strip()
        if not (api_key and secret):
            logger.warning("Baidu ASR requires API Key + Secret Key")
            return ""

        try:
            async with make_pinned_async_client(_TOKEN_URL, timeout=20.0) as client:
                tr = await client.get(
                    _TOKEN_URL,
                    params={
                        "grant_type": "client_credentials",
                        "client_id": api_key,
                        "client_secret": secret,
                    },
                )
                tr.raise_for_status()
                token = (tr.json() or {}).get("access_token") or ""
        except Exception as e:
            logger.error("Baidu ASR token failed: %s", e)
            return ""
        if not token:
            return ""

        try:
            wav = pcm_base64_to_wav_bytes(pcm_b64, sample_rate)
            speech = base64.b64encode(wav).decode("ascii")
        except Exception as e:
            logger.warning("Baidu ASR audio preparation failed: %s", e)
            return ""

        body = {
            "format": "wav",
            "rate": sample_rate,
            "channel": 1,
            "cuid": "mock-interview",
            "token": token,
            "speech": speech,
            "len": len(wav),
            "dev_pid": 1537,
        }
        try:
            async with make_pinned_async_client(_ASR_URL, timeout=25.0) as client:
                resp = await client.post(_ASR_URL, json=body)
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            logger.error("Baidu ASR failed: %s", e)
            return ""

        if payload.get("err_no") not in (0, None):
            logger.error("Baidu ASR err=%s %s", payload.get("err_no"), payload.get("err_msg"))
            return ""
        results = payload.get("result") or []
        if isinstance(results, list) and results:
            return str(results[0]).strip()
        return ""
