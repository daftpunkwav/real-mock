"""From-DB construction tests for apps/api/src/realmock/platform/capabilities/ai/llm/client/from_db.py.

Covers: build_from_db/build_from_stage_config including reasoning-capability gating,
env fallback, secret decryption and legacy-format error branches.

Conventions: no DB, no network (pipeline config and secrets mocked); asyncio_mode=auto.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from realmock.platform.capabilities.ai.llm.client import from_db as fd_mod
from realmock.platform.capabilities.ai.llm.client.from_db import build_from_db, build_from_stage_config
from realmock.platform.core.secrets import LegacySecretFormatError

_RUNTIME_CFG = "realmock.platform.services.pipeline.config.get_stage_config_for_runtime"


class _FakeClient:
    def __init__(self, **kw: Any) -> None:
        self.kw = kw


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        llm_max_tokens=4096,
        llm_api_base="https://env-base",
        llm_api_key="env-key",
        llm_model="env-model",
    )


def _patch(
    cfg: dict[str, Any],
    decrypt: Any = None,
) -> Any:
    ctx = patch(_RUNTIME_CFG, return_value=cfg)
    ctx2 = patch.object(fd_mod, "get_settings", return_value=_settings())
    ctx3 = patch.object(fd_mod, "decrypt_secret", side_effect=(lambda v: v) if decrypt is None else decrypt)
    return (ctx, ctx2, ctx3)


def test_full_profile_with_reasoning() -> None:
    cfg = {
        "api_base": "https://x", "api_key": "k", "model": "m", "max_tokens": 111,
        "protocol": "anthropic_messages", "reasoning_capable": True,
        "context_window": 99, "supports_vision": True,
    }
    ctx, ctx2, ctx3 = _patch(cfg)
    with ctx, ctx2, ctx3:
        out = build_from_db(_FakeClient, MagicMock(), reasoning_effort="high")  # type: ignore[arg-type]
    assert out.kw["api_base"] == "https://x"
    assert out.kw["model"] == "m"
    assert out.kw["max_tokens"] == 111
    assert out.kw["protocol"] == "anthropic_messages"
    assert out.kw["reasoning_effort"] == "high"
    assert out.kw["supports_vision"] is True


def test_reasoning_dropped_without_capability() -> None:
    cfg = {"api_base": "https://x", "api_key": "k", "model": "m", "reasoning_capable": False}
    ctx, ctx2, ctx3 = _patch(cfg)
    with ctx, ctx2, ctx3:
        out = build_from_db(_FakeClient, MagicMock(), reasoning_effort="high")  # type: ignore[arg-type]
    assert out.kw["reasoning_effort"] is None


def test_explicit_profile_without_credentials_keeps_identity() -> None:
    cfg = {"profile_id": 7, "api_base": "", "model": "m7", "protocol": "openai_chat"}
    ctx, ctx2, ctx3 = _patch(cfg)
    with ctx, ctx2, ctx3:
        out = build_from_db(_FakeClient, MagicMock(), profile_id=7)  # type: ignore[arg-type]
    assert out.kw["api_key"] == ""
    assert out.kw["api_base"] == ""
    assert out.kw["model"] == "m7"


def test_env_fallback_decrypts_key() -> None:
    ctx, ctx2, ctx3 = _patch({}, decrypt=lambda v: "dec-" + v)
    with ctx, ctx2, ctx3:
        out = build_from_db(_FakeClient, MagicMock())  # type: ignore[arg-type]
    assert out.kw["api_base"] == "https://env-base"
    assert out.kw["api_key"] == "dec-env-key"
    assert out.kw["model"] == "env-model"
    assert out.kw["max_tokens"] == 4096
    assert out.kw["reasoning_effort"] is None


def test_env_fallback_decrypt_failures_blank_key() -> None:
    for err in (LegacySecretFormatError("old"), ValueError("bad")):
        ctx = patch(_RUNTIME_CFG, return_value={})
        ctx2 = patch.object(fd_mod, "get_settings", return_value=_settings())
        ctx3 = patch.object(fd_mod, "decrypt_secret", side_effect=err)
        with ctx, ctx2, ctx3:
            out = build_from_db(_FakeClient, MagicMock())  # type: ignore[arg-type]
        assert out.kw["api_key"] == ""


def test_from_stage_config_plain_and_enc() -> None:
    out = build_from_stage_config(_FakeClient, {"api_base": "b", "api_key": "k", "model": "m"})  # type: ignore[arg-type]
    assert out.kw["api_key"] == "k"
    with patch.object(fd_mod, "decrypt_secret", return_value="plain"):
        out2 = build_from_stage_config(_FakeClient, {"api_base": "b", "api_key": "enc:v2:x", "model": "m"})  # type: ignore[arg-type]
    assert out2.kw["api_key"] == "plain"


def test_from_stage_config_enc_failures_blank_key() -> None:
    with patch.object(
        fd_mod, "decrypt_secret", side_effect=LegacySecretFormatError("old")
    ):
        out = build_from_stage_config(_FakeClient, {"api_key": "enc:v1:old"})  # type: ignore[arg-type]
    assert out.kw["api_key"] == ""
    with patch.object(fd_mod, "decrypt_secret", side_effect=ValueError("bad")):
        out2 = build_from_stage_config(_FakeClient, {"api_key": "enc:bad"})  # type: ignore[arg-type]
    assert out2.kw["api_key"] == ""
    assert fd_mod.__all__ == ["build_from_db", "build_from_stage_config"]
