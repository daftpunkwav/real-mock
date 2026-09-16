"""Adapted-vendor registry: JSON descriptors under ``defs/`` describe each vendor's
deeply adapted request templates (one file per vendor).

The three voice/reasoning catalog tables (``voice/config``) stay the runtime SSOT for
provider ids and credentials routing; this package adds the vendor dimension on top:

- :func:`vendor_def` / :func:`is_vendor_adapted` — adapter lookup ("is this vendor adapted?");
- :func:`recommended_vendors_payload` — the two-level recommended-vendor tree
  (level 1 vendor, level 2 model type) consumed by the settings page.

Vendors register by dropping a JSON file into ``defs/``; no code change is needed.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from realmock.platform.capabilities.voice.config.catalog import catalog_payload

logger = logging.getLogger(__name__)

_DEFS_DIR = Path(__file__).resolve().parent / "defs"

#: Capability names shared with the voice/reasoning catalog tables.
CAPABILITIES = ("reasoning", "recognize", "speak")

#: Vendor ids that are not real suppliers (built-in / generic / placeholders); they are
#: excluded from the recommended-vendor tree.
_NON_VENDOR_IDS = frozenset({"custom", "local", "edge", "none"})

#: vendor group id → display label (groups several catalog provider ids of one company).
VENDOR_LABELS: dict[str, str] = {
    "minimax": "MiniMax",
    "openai": "OpenAI",
    "deepseek": "DeepSeek",
    "stepfun": "StepFun",
    "openrouter": "OpenRouter",
    "xiaomi": "小米 MiMo",
    "iflytek": "科大讯飞",
    "volcengine": "火山引擎(豆包)",
    "alibaba": "阿里云",
    "tencent": "腾讯云",
    "baidu": "百度",
    "zhipu": "智谱",
}


@lru_cache(maxsize=1)
def _load_defs() -> dict[str, dict[str, Any]]:
    """Parse every vendor descriptor JSON under ``defs/`` (id → def)."""
    defs: dict[str, dict[str, Any]] = {}
    for path in sorted(_DEFS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.error("Vendor def %s is not valid JSON; skipped", path.name, exc_info=True)
            continue
        vendor_id = str(data.get("vendor") or "").strip()
        if vendor_id:
            defs[vendor_id] = data
    return defs


def vendor_def(vendor_id: str) -> dict[str, Any] | None:
    """Deep adapter descriptor for ``vendor_id``, or None when the vendor has no JSON def."""
    return _load_defs().get((vendor_id or "").strip())


def is_vendor_adapted(vendor_id: str, capability: str) -> bool:
    """Whether ``vendor_id`` has a ready adapter for ``capability``.

    A vendor is adapted when a deep JSON def declares the capability, or the voice/reasoning
    catalog tables list a ready provider entry for it. User-typed unknown vendors fail this
    check by design: they are adapted through a settings-side JSON descriptor instead.
    """
    vendor_id = (vendor_id or "").strip()
    capability = (capability or "").strip()
    if not vendor_id or capability not in CAPABILITIES:
        return False
    capability_def = (vendor_def(vendor_id) or {}).get("capabilities", {}).get(capability)
    if isinstance(capability_def, dict):
        return True
    for provider in catalog_payload().get(capability, []):
        if provider.get("vendor") == vendor_id and provider.get("status") == "ready":
            return True
    return False


def recommended_vendors_payload() -> dict[str, Any]:
    """Two-level recommended-vendor tree: level 1 vendor → level 2 model types.

    Only vendors with at least one ready capability are listed; ``custom`` / ``local``
    / placeholders are never recommended. Each capability entry carries the catalog
    prefill (ids/defaults) plus, when a deep def exists, its request template metadata
    (``adapted=True`` and the ``def`` block).
    """
    catalogs = catalog_payload()
    grouped: dict[str, dict[str, Any]] = {}
    for capability in CAPABILITIES:
        for provider in catalogs.get(capability, []):
            vendor_id = str(provider.get("vendor") or "").strip()
            if not vendor_id or provider.get("status") != "ready":
                continue
            if provider.get("id") in _NON_VENDOR_IDS:
                continue
            entry = {
                "provider_id": provider.get("id") or "",
                "label": _CAPABILITY_LABELS.get(capability, capability),
                "catalog_label": provider.get("label") or "",
                "default_model": provider.get("default_model") or "",
                "default_api_base": provider.get("default_api_base") or "",
                "hint": provider.get("hint") or "",
                "adapted": False,
            }
            capability_def = (vendor_def(vendor_id) or {}).get("capabilities", {}).get(capability)
            if isinstance(capability_def, dict):
                entry["adapted"] = True
                entry["def"] = {
                    "transport": capability_def.get("transport") or "",
                    "models": list(capability_def.get("models") or []),
                    "request": capability_def.get("request") or {},
                    "notes": capability_def.get("notes") or "",
                }
                entry["default_model"] = entry["default_model"] or capability_def.get("default_model") or ""
                entry["default_api_base"] = entry["default_api_base"] or capability_def.get("default_api_base") or ""
            grouped.setdefault(vendor_id, {})[capability] = entry

    vendors = []
    for vendor_id in sorted(grouped, key=lambda v: (v != "minimax", v)):
        capabilities = grouped[vendor_id]
        vdef = vendor_def(vendor_id) or {}
        docs = vdef.get("docs") or {}
        # Descriptor label wins so a new defs/*.json stays self-contained (no code
        # change needed to register a vendor); the code table only backfills
        # catalog-only vendors that have no def file.
        label = vdef.get("label") or VENDOR_LABELS.get(vendor_id, vendor_id)
        vendors.append(
            {
                "id": vendor_id,
                "label": label,
                "docs": docs,
                "capabilities": capabilities,
            }
        )
    return {"vendors": vendors}


_CAPABILITY_LABELS = {
    "reasoning": "思考模型",
    "recognize": "语音识别 STT",
    "speak": "语音合成 TTS",
}


__all__ = [
    "CAPABILITIES",
    "VENDOR_LABELS",
    "is_vendor_adapted",
    "recommended_vendors_payload",
    "vendor_def",
]
