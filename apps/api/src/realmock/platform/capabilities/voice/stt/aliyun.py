"""Alibaba Cloud Sentence Speech Recognition (NLS)."""

from __future__ import annotations

import json
import logging

from realmock.platform.core.security import make_pinned_async_client
from realmock.platform.capabilities.voice.stt.base import SttCredentials
from realmock.platform.capabilities.voice.stt.whisper import pcm_base64_to_wav_bytes

logger = logging.getLogger(__name__)


class AliyunProvider:
    async def transcribe(
        self, pcm_b64: str, *, sample_rate: int, creds: SttCredentials
    ) -> str:
        app_key = (creds.app_key or creds.app_id or "").strip()
        # api_key is treated primarily as the NLS Token; api_secret is the AccessKeySecret (optional)
        token = (creds.api_key or "").strip()
        if not app_key or not token:
            logger.warning("Alibaba Cloud ASR requires AppKey + Token (fill in the ASR API Key)")
            return ""

        try:
            wav = pcm_base64_to_wav_bytes(pcm_b64, sample_rate)
        except Exception as e:
            logger.warning("Alibaba Cloud ASR audio preparation failed: %s", e)
            return ""

        url = (
            "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/asr"
            f"?appkey={app_key}&format=wav&sample_rate={sample_rate}"
            "&enable_punctuation_prediction=true"
            "&enable_inverse_text_normalization=true"
        )
        headers = {
            "X-NLS-Token": token,
            "Content-Type": "application/octet-stream",
        }
        try:
            async with make_pinned_async_client(url, timeout=45.0) as client:
                resp = await client.post(url, headers=headers, content=wav)
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            logger.error("Alibaba Cloud ASR failed: %s", e)
            return ""

        if payload.get("status") not in (0, 20000000, None):
            # Success common status=20000000
            if payload.get("status") != 20000000 and "result" not in payload:
                logger.error("Alibaba Cloud ASR error: %s", json.dumps(payload, ensure_ascii=False)[:200])
                return ""
        return str(payload.get("result") or "").strip()
