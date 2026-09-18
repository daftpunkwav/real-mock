"""MiniMax Speech TTS adapter (T2A HTTP, POST /v1/t2a_v2).

Request shape is driven by the vendor descriptor (``platform/vendors/defs/minimax.json``);
every field of the request body can be overridden per model entry via
``extras["tts_request"]`` (deep-merged onto the descriptor defaults).

Session prosody (``emotion`` tag plus edge-tts-style ``rate``/``pitch`` strings) is
translated to native ``voice_setting`` fields through the descriptor's ``prosody``
section and only applied for non-neutral/non-zero values.

Text-markup support (all passed through to the API verbatim):
- pause markers ``<#x#>`` (x seconds, 0.01-99.99);
- inline pronunciation replacement ``(pinyin5)`` / ``(ipa)`` / ``(jyutping6)``;
- interjection tags ``(laughs)`` etc. — only speech-2.8-hd / speech-2.8-turbo
  (see :func:`supports_interjections`).

Long text: the API caps a request at 10000 chars and recommends streaming over 3000;
streaming is not wired, so this adapter splits at paragraph/sentence boundaries and
concatenates the chunked audio (mp3/flac/opus/pcm concatenate cleanly; wav does not —
only the first chunk is returned with a warning in that case).
"""

from __future__ import annotations

import base64
import logging
import re

import httpx

from realmock.platform.config import get_settings
from realmock.platform.core.security import make_pinned_async_client
from realmock.platform.vendors import vendor_def
from realmock.platform.vendors.templates import deep_merge, get_dotted

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "speech-2.8-hd"
DEFAULT_VOICE = "male-qn-qingse"
DEFAULT_BASE = "https://api.minimaxi.com/v1"

# Formats whose byte streams can be concatenated chunk-by-chunk without a container header.
_CONCATENATABLE_FORMATS = frozenset({"mp3", "flac", "opus", "pcm", "pcmu_raw"})

# Built-in floor defaults, used only when the vendor descriptor fails to load.
_FALLBACK_BODY: dict = {
    "stream": False,
    "voice_setting": {"speed": 1.0, "vol": 1.0, "pitch": 0},
    "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
}


def _capability_def() -> dict:
    capability = (vendor_def("minimax") or {}).get("capabilities", {}).get("speak")
    return capability if isinstance(capability, dict) else {}


def _endpoint_path(fallback: str) -> str:
    """Descriptor-declared endpoint path (leading slash normalized), or ``fallback``."""
    path = str(_capability_def().get("endpoint_path") or fallback).strip()
    return path if path.startswith("/") else f"/{path}"


def _resolve_voice(voice: str) -> str:
    # "mimo_default" is the generic custom-processor default, not a MiniMax voice id.
    v = (voice or "").strip()
    return DEFAULT_VOICE if v in ("", "mimo_default") else v


def supports_interjections(model: str) -> bool:
    """Whether the TTS model renders interjection tags instead of reading them aloud."""
    supported = (
        (_capability_def().get("text_markup", {}).get("interjections", {}) or {}).get("models")
        or ["speech-2.8-hd", "speech-2.8-turbo"]
    )
    m = (model or "").strip().lower()
    return any(m == str(s).lower() for s in supported)


def interjection_tags() -> list[str]:
    """Interjection tags the supported models accept (descriptor-driven)."""
    tags = (
        (_capability_def().get("text_markup", {}).get("interjections", {}) or {}).get("tags")
        or []
    )
    return [str(t) for t in tags]


def resolve_minimax_voice(avatar_id: str | None, settings_voice: str | None) -> str:
    """Pick the MiniMax voice for a session: avatar mapping ← explicit vendor voice ← default.

    A settings voice counts as vendor-native when it appears in the descriptor's voice
    tables or matches the ``male-``/``female-``/``presenter_`` id shapes; anything else
    (e.g. an Edge neural id) is ignored so avatars stay in charge.
    """
    voices = _capability_def().get("voices", {}) or {}
    default = str(voices.get("default") or DEFAULT_VOICE)
    aid = (avatar_id or "").strip()
    mapped = (voices.get("avatar_map") or {}).get(aid)
    if mapped:
        return str(mapped)
    settings_voice = (settings_voice or "").strip()
    if settings_voice and re.match(r"^(male-|female-|presenter_)", settings_voice):
        return settings_voice
    for item in voices.get("recommended") or []:
        if isinstance(item, dict) and item.get("id") == settings_voice:
            return settings_voice
    return default


def split_text_chunks(text: str, limit: int) -> list[str]:
    """Split text into chunks under ``limit`` at paragraph, then sentence, boundaries.

    A single sentence longer than ``limit`` is hard-sliced so every chunk stays within
    the API's per-request cap.
    """
    text = (text or "").strip()
    if len(text) <= limit:
        return [text] if text else []
    chunks: list[str] = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        current = ""
        pieces = re.split(r"(?<=[。！？!?；;…])", paragraph)
        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            if len(piece) > limit:
                # Hard-slice an over-long sentence.
                for i in range(0, len(piece), limit):
                    if current:
                        chunks.append(current)
                        current = ""
                    chunks.append(piece[i : i + limit])
                continue
            if len(current) + len(piece) > limit:
                chunks.append(current)
                current = piece
            else:
                current = f"{current}{piece}" if current else piece
        if current:
            chunks.append(current)
    return chunks


def build_tts_body(
    text: str,
    *,
    model: str,
    voice: str,
    overrides: dict | None = None,
    emotion: str = "neutral",
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> dict:
    """Assemble the t2a_v2 body: descriptor defaults ← extras overrides ← runtime values ← prosody.

    ``emotion``/``rate``/``pitch`` carry the session prosody (edge-tts-style ``"+12%"`` /
    ``"+2Hz"`` strings plus a coarse emotion tag). They are translated through the
    descriptor's ``prosody`` section and only applied when non-neutral/non-zero, so a
    pinned ``extras["tts_request"]`` value survives for neutral sentences. When prosody
    is active the two axes differ: ``speed`` is recomputed from the descriptor base
    (replacing a pinned speed), while ``pitch`` accumulates onto the pinned value.
    """
    request_def = _capability_def().get("request") or {}
    body = deep_merge(request_def.get("body") or _FALLBACK_BODY, overrides)
    body["model"] = model or DEFAULT_MODEL
    body["text"] = text
    body.setdefault("stream", False)
    voice_setting = dict(body.get("voice_setting") or {})
    voice_setting["voice_id"] = _resolve_voice(voice)
    body["voice_setting"] = voice_setting
    return apply_prosody(body, emotion=emotion, rate=rate, pitch=pitch)


def _parse_percent(rate: str) -> int:
    """Parse an edge-tts style relative rate (``"+12%"`` → 12, ``"-3%"`` → -3)."""
    try:
        return int(str(rate or "").strip().replace("%", ""))
    except ValueError:
        return 0


def _parse_hz(pitch: str) -> int:
    """Parse an edge-tts style pitch offset (``"+2Hz"`` → 2, ``"-1hz"`` → -1)."""
    try:
        return int(str(pitch or "").strip().replace("Hz", "").replace("hz", ""))
    except ValueError:
        return 0


def apply_prosody(
    body: dict,
    *,
    emotion: str = "neutral",
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> dict:
    """Overlay session prosody onto ``body["voice_setting"]`` per the descriptor prosody map.

    Only non-neutral emotions and non-zero rate/pitch offsets are written, so static
    values from the descriptor defaults or ``extras["tts_request"]`` win otherwise.
    """
    prosody = _capability_def().get("prosody")
    if not isinstance(prosody, dict):
        return body
    voice_setting = dict(body.get("voice_setting") or {})

    emo = (emotion or "neutral").strip().lower()
    emotion_map = prosody.get("emotion_map") or {}
    native = str(emotion_map.get(emo) or "").strip()
    if native:
        voice_setting["emotion"] = native

    pct = _parse_percent(rate)
    if pct:
        speed_cfg = prosody.get("speed") or {}
        base = float(speed_cfg.get("base", 1.0))
        lo = float(speed_cfg.get("min", 0.5))
        hi = float(speed_cfg.get("max", 2.0))
        voice_setting["speed"] = round(min(max(base * (1 + pct / 100), lo), hi), 2)

    hz = _parse_hz(pitch)
    if hz:
        pitch_cfg = prosody.get("pitch") or {}
        lo = int(pitch_cfg.get("min", -12))
        hi = int(pitch_cfg.get("max", 12))
        try:
            current = int(float(voice_setting.get("pitch") or 0))
        except (TypeError, ValueError):
            current = 0
        voice_setting["pitch"] = min(max(current + hz, lo), hi)

    body["voice_setting"] = voice_setting
    return body


async def _synthesize_chunk(body: dict, url: str, api_key: str) -> str:
    """POST one t2a_v2 request and return the audio as base64 ("" on failure).

    MiniMax normally returns hex; non-hex payloads are treated as base64. A value that
    is neither is passed through unchanged (legacy tolerance) — multi-chunk callers
    that cannot concatenate it will then return empty.
    """
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    settings = get_settings()
    try:
        async with make_pinned_async_client(
            url,
            allow_local=settings.allow_local_llm,
            require_https=bool(settings.is_prod),
            timeout=60.0,
        ) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            payload = resp.json()
    except httpx.HTTPStatusError as e:
        body_txt = ""
        try:
            body_txt = (e.response.text or "")[:200]
        except Exception:
            logger.debug("Failed to read TTS error response body", exc_info=True)
        logger.error("MiniMax TTS HTTP %s: %s", e.response.status_code, body_txt)
        return ""
    except Exception as e:
        logger.error("MiniMax TTS failed: %s", e)
        return ""

    base_resp = payload.get("base_resp") or {}
    if isinstance(base_resp, dict) and base_resp.get("status_code") not in (None, 0):
        logger.error(
            "MiniMax TTS base_resp status=%s msg=%s",
            base_resp.get("status_code"),
            base_resp.get("status_msg"),
        )
        return ""

    response_def = _capability_def().get("response", {}) or {}
    audio_path = str(response_def.get("audio_path") or "data.audio")
    audio = get_dotted(payload, audio_path) or payload.get("audio") or ""
    if not (isinstance(audio, str) and audio):
        logger.warning(
            "MiniMax TTS response has no audio field keys=%s", list(payload.keys())[:8]
        )
        return ""
    if str(response_def.get("encoding") or "hex") == "hex":
        try:
            return base64.b64encode(bytes.fromhex(audio)).decode("ascii")
        except ValueError:
            pass
    try:
        return base64.b64encode(base64.b64decode(audio, validate=True)).decode("ascii")
    except Exception:
        return audio


async def synthesize_minimax_to_base64(
    text: str,
    *,
    api_key: str,
    api_base: str = DEFAULT_BASE,
    model: str = DEFAULT_MODEL,
    voice: str = DEFAULT_VOICE,
    overrides: dict | None = None,
    emotion: str = "neutral",
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> str:
    """Call MiniMax t2a_v2; successfully returns mp3/wav base64, otherwise returns an empty string."""
    key = (api_key or "").strip()
    clean = (text or "").strip()
    if not key or not clean:
        return ""

    # Full-URL mode passes the verbatim t2a_v2 endpoint; otherwise the descriptor's
    # documented endpoint path is appended (literal fallback when the descriptor fails to load).
    base = (api_base or DEFAULT_BASE).rstrip("/")
    path = _endpoint_path("/t2a_v2")
    url = base if base.endswith(path) else f"{base}{path}"

    merged_body = build_tts_body(
        clean,
        model=model,
        voice=voice,
        overrides=overrides,
        emotion=emotion,
        rate=rate,
        pitch=pitch,
    )
    fmt = str((merged_body.get("audio_setting") or {}).get("format") or "mp3").lower()
    limit = int(_capability_def().get("limits", {}).get("chunk_chars") or 2800)
    chunks = split_text_chunks(clean, limit)
    if len(chunks) > 1 and fmt not in _CONCATENATABLE_FORMATS:
        logger.warning(
            "MiniMax TTS format %s cannot be chunk-concatenated; synthesizing only the first chunk", fmt
        )
        chunks = chunks[:1]

    audio_parts: list[str] = []
    for chunk in chunks:
        body = dict(merged_body)
        body["text"] = chunk
        part = await _synthesize_chunk(body, url, key)
        if not part:
            return ""
        audio_parts.append(part)
    if len(audio_parts) == 1:
        return audio_parts[0]
    # Multi-chunk: concatenate the raw audio streams (possible only when every chunk
    # decoded to real bytes; legacy passthrough strings bail out here).
    try:
        total = b"".join(base64.b64decode(part) for part in audio_parts)
    except Exception:
        logger.warning("MiniMax TTS multi-chunk audio was not decodable; returning empty")
        return ""
    return base64.b64encode(total).decode("ascii")
