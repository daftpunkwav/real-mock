"""Tencent Cloud sentence recognition."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time

from realmock.platform.core.security import make_pinned_async_client
from realmock.platform.capabilities.voice.stt.base import SttCredentials
from realmock.platform.capabilities.voice.stt.whisper import pcm_base64_to_wav_bytes

logger = logging.getLogger(__name__)

_HOST = "asr.tencentcloudapi.com"
_SERVICE = "asr"
_ACTION = "SentenceRecognition"
_VERSION = "2019-06-14"


def _sign_tc3(
    *,
    secret_id: str,
    secret_key: str,
    payload: str,
    timestamp: int,
) -> dict[str, str]:
    date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))
    http_request_method = "POST"
    canonical_uri = "/"
    canonical_querystring = ""
    canonical_headers = (
        f"content-type:application/json; charset=utf-8\nhost:{_HOST}\n"
    )
    signed_headers = "content-type;host"
    hashed_request_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = (
        f"{http_request_method}\n{canonical_uri}\n{canonical_querystring}\n"
        f"{canonical_headers}\n{signed_headers}\n{hashed_request_payload}"
    )
    credential_scope = f"{date}/{_SERVICE}/tc3_request"
    string_to_sign = (
        "TC3-HMAC-SHA256\n"
        f"{timestamp}\n"
        f"{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )

    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    secret_date = _hmac(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = _hmac(secret_date, _SERVICE)
    secret_signing = _hmac(secret_service, "tc3_request")
    signature = hmac.new(
        secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    authorization = (
        "TC3-HMAC-SHA256 "
        f"Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "Authorization": authorization,
        "Content-Type": "application/json; charset=utf-8",
        "Host": _HOST,
        "X-TC-Action": _ACTION,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Version": _VERSION,
    }


class TencentProvider:
    async def transcribe(
        self, pcm_b64: str, *, sample_rate: int, creds: SttCredentials
    ) -> str:
        app_id = (creds.app_id or "").strip()
        secret_id = (creds.api_key or "").strip()
        secret_key = (creds.api_secret or "").strip()
        if not (secret_id and secret_key):
            logger.warning("Tencent Cloud ASR requires SecretId + SecretKey")
            return ""

        try:
            wav = pcm_base64_to_wav_bytes(pcm_b64, sample_rate)
            data_b64 = base64.b64encode(wav).decode("ascii")
        except Exception as e:
            logger.warning("Tencent Cloud ASR audio preparation failed: %s", e)
            return ""

        body: dict = {
            "EngSerViceType": "16k_zh",
            "SourceType": 1,
            "VoiceFormat": "wav",
            "Data": data_b64,
            "DataLen": len(wav),
        }
        if app_id.isdigit():
            body["ProjectId"] = 0
            body["SubServiceType"] = 2

        payload = json.dumps(body)
        ts = int(time.time())
        headers = _sign_tc3(
            secret_id=secret_id, secret_key=secret_key, payload=payload, timestamp=ts
        )
        try:
            async with make_pinned_async_client(
                f"https://{_HOST}", timeout=25.0
            ) as client:
                resp = await client.post(
                    f"https://{_HOST}", headers=headers, content=payload
                )
                resp.raise_for_status()
                payload_json = resp.json()
        except Exception as e:
            logger.error("Tencent Cloud ASR failed: %s", e)
            return ""

        resp_obj = payload_json.get("Response") or {}
        if resp_obj.get("Error"):
            logger.error("Tencent Cloud ASR Error: %s", resp_obj["Error"])
            return ""
        return str(resp_obj.get("Result") or "").strip()
