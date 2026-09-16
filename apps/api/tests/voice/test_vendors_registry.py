"""Adapted-vendor registry tests (platform/vendors).

Covers: descriptor loading, ``is_vendor_adapted`` semantics (deep JSON def vs
catalog-ready fallback vs unknown vendors), and the recommended-vendors payload
shape consumed by the settings page (vendor grouping, exclusions, adapted flags).
"""

from __future__ import annotations

from realmock.platform.vendors import (
    is_vendor_adapted,
    recommended_vendors_payload,
    vendor_def,
)


def test_vendor_def_loads_minimax_descriptor():
    data = vendor_def("minimax")
    assert data is not None
    assert data["label"] == "MiniMax"
    caps = data["capabilities"]
    assert {"reasoning", "recognize", "speak"} <= set(caps)
    # The language hint header is intentionally absent by default (mixed-language).
    assert "language" not in caps["recognize"]["request"]["headers"]
    assert caps["speak"]["request"]["body"]["audio_setting"]["format"] == "mp3"


def test_vendor_def_unknown_vendor_returns_none():
    assert vendor_def("does-not-exist") is None


def test_is_vendor_adapted_semantics():
    # Deep JSON def present.
    assert is_vendor_adapted("minimax", "recognize") is True
    assert is_vendor_adapted("minimax", "speak") is True
    assert is_vendor_adapted("minimax", "reasoning") is True
    # Catalog-ready fallback (xfyun has a Python adapter but no JSON def).
    assert is_vendor_adapted("iflytek", "recognize") is True
    # Unknown vendor / bad capability.
    assert is_vendor_adapted("some-vendor", "stt") is False
    assert is_vendor_adapted("minimax", "unknown") is False
    assert is_vendor_adapted("", "speak") is False


def test_recommended_payload_groups_by_vendor():
    payload = recommended_vendors_payload()
    vendors = {v["id"]: v for v in payload["vendors"]}
    assert "minimax" in vendors
    # Placeholder/built-in entries are never recommended.
    assert "custom" not in vendors
    assert "local" not in vendors

    minimax = vendors["minimax"]
    assert minimax["label"] == "MiniMax"
    assert set(minimax["capabilities"]) == {"reasoning", "recognize", "speak"}
    for cap in minimax["capabilities"].values():
        assert cap["adapted"] is True
        assert isinstance(cap["def"].get("request"), dict)
    assert minimax["capabilities"]["speak"]["provider_id"] == "minimax_speech"
    assert minimax["capabilities"]["recognize"]["provider_id"] == "minimax"


def test_recommended_payload_excludes_coming_soon():
    payload = recommended_vendors_payload()
    for vendor in payload["vendors"]:
        for cap in vendor["capabilities"].values():
            assert cap["provider_id"] != "zhipu_glm4_voice"
            assert cap["provider_id"] != "doubao_s2s"


def test_every_recommended_vendor_has_at_least_one_ready_capability():
    for vendor in recommended_vendors_payload()["vendors"]:
        assert vendor["capabilities"], vendor["id"]
