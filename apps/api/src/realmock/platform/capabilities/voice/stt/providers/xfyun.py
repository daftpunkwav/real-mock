"""iFlytek Voice Dictation (Short Audio WebAPI)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime
from time import mktime
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time


from realmock.platform.capabilities.voice.stt.base import SttCredentials

logger = logging.getLogger(__name__)

_HOST = "iat-api.xfyun.cn"
_PATH = "/v2/iat"
_URL = f"https://{_HOST}{_PATH}"


def _auth_url(*, api_key: str, api_secret: str) -> str:
    now = datetime.now()
    date = format_date_time(mktime(now.timetuple()))
    signature_origin = f"host: {_HOST}\ndate: {date}\nGET {_PATH} HTTP/1.1"
    signature_sha = hmac.new(
        api_secret.encode("utf-8"),
        signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    signature = base64.b64encode(signature_sha).decode("utf-8")
    authorization_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")
    return _URL + "?" + urlencode({"authorization": authorization, "date": date, "host": _HOST})


class XfyunProvider:
    """iFlytek Dictation: Submit the entire PCM as one frame (suitable for short sentence connectivity tests and short speeches)."""

    async def transcribe(
        self, pcm_b64: str, *, sample_rate: int, creds: SttCredentials
    ) -> str:
        app_id = (creds.app_id or "").strip()
        api_key = (creds.api_key or "").strip()
        api_secret = (creds.api_secret or "").strip()
        if not (app_id and api_key and api_secret):
            logger.warning("iFlytek ASR is missing AppId/APIKey/APISecret")
            return ""

        # Send raw PCM directly within the frame; only base64 validity is verified here (no wav container use)
        try:
            base64.b64decode(pcm_b64)
        except Exception as e:
            logger.warning("iFlytek ASR audio preparation failed: %s", e)
            return ""

        # iFlytek's official short connection dictation uses WSS; its compatible HTTP proxy single frame is used here (available in some areas)
        # More robust: use websocket. To minimize dependencies, use websockets when available; otherwise use httpx and return empty on failure.
        try:
            import websockets
        except ImportError:
            logger.error("iFlytek ASR requires the websockets package")
            return ""

        auth = _auth_url(api_key=api_key, api_secret=api_secret).replace("https://", "wss://")
        business = {
            "language": "zh_cn",
            "domain": "iat",
            "accent": "mandarin",
            "vad_eos": 3000,
            "dwa": "wpgs",
        }
        common = {"app_id": app_id}
        texts: list[str] = []

        try:
            async with websockets.connect(auth, max_size=8 * 1024 * 1024) as ws:
                # Sent once (status=2 means the last frame)
                frame = {
                    "common": common,
                    "business": business,
                    "data": {
                        "status": 2,
                        "format": "audio/L16;rate=16000",
                        "encoding": "raw",
                        "audio": base64.b64encode(
                            base64.b64decode(pcm_b64)
                        ).decode("ascii"),
                    },
                }
                await ws.send(json.dumps(frame))
                while True:
                    # Bound each server frame: a stalled peer must not leave the
                    # transcription coroutine pending forever (every other
                    # provider enforces an HTTP timeout instead).
                    raw = await asyncio.wait_for(ws.recv(), timeout=15.0)
                    payload = json.loads(raw)
                    code = payload.get("code", -1)
                    if code != 0:
                        logger.error("iFlytek ASR code=%s msg=%s", code, payload.get("message"))
                        break
                    data = payload.get("data") or {}
                    result = data.get("result") or {}
                    ws_list = result.get("ws") or []
                    for block in ws_list:
                        for cw in block.get("cw") or []:
                            w = cw.get("w") or ""
                            if w:
                                texts.append(w)
                    if data.get("status") == 2:
                        break
        except Exception as e:
            logger.error("iFlytek ASR failed: %s", e)
            return ""

        return "".join(texts).strip()
