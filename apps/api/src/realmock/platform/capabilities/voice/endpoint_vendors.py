"""Full-URL vendor matching: signature path fragments → vendor id.

In full-URL mode a provider's api_base is a complete endpoint URL, and the request path is the
only reliable vendor signal (each vendor owns distinct endpoint paths). A vendor adapter is
selected only when its signature appears in the URL path; unknown endpoints never guess.
"""

from __future__ import annotations

from urllib.parse import urlparse

# capability → {path signature: vendor id}; add one entry per newly adapted vendor.
STT_PATHS: dict[str, str] = {
    "speech_to_text": "minimax",
}
TTS_PATHS: dict[str, str] = {
    "t2a_v2": "minimax",
}


def match_vendor(url: str, table: dict[str, str]) -> str:
    """Return the vendor id whose signature appears in the URL path, or "" when none matches."""
    path = urlparse((url or "").strip()).path.strip("/")
    if not path:
        return ""
    for signature, vendor in table.items():
        if signature in path:
            return vendor
    return ""


__all__ = ["STT_PATHS", "TTS_PATHS", "match_vendor"]
