"""LLMClient.embed configuration regressions: dedicated embeddings base, chat-base fallback, decrypt fail-closed."""

from __future__ import annotations

from typing import Any

import pytest

from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.config import Settings, get_settings


def _make_settings(**overrides: Any) -> Settings:
    base = {
        "llm_api_base": "https://api.stepfun.com/v1",
        "llm_api_key": "sk-test",
        "llm_model": "step-3.7-flash",
        "rag_backend": "local",
    }
    base.update(overrides)
    return Settings(**base)


def test_llm_client_embed_uses_dedicated_embeddings_base(monkeypatch) -> None:
    """``LLM_EMBEDDINGS_BASE`` should take precedence over ``LLM_API_BASE`` for embeddings calls."""
    captured: dict[str, Any] = {}

    class _StubResp:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

        def raise_for_status(self) -> None:
            return None

    class _StubClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, **kw):
            captured["url"] = url
            return _StubResp()

    # embed has been split up: URL validation is in llm_client_ext, while request execution is in openai_transport.
    import realmock.platform.capabilities.ai.llm.client.llm_client_ext as llm_mod
    import realmock.platform.capabilities.ai.llm.client.openai_transport as ot_mod

    monkeypatch.setattr(ot_mod, "make_pinned_async_client", lambda *a, **kw: _StubClient())
    # Reset the settings cache so this test reads an isolated embeddings base.
    get_settings.cache_clear()

    monkeypatch.setenv("LLM_API_BASE", "https://api.openai.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-chat")
    monkeypatch.setenv("LLM_EMBEDDINGS_BASE", "https://api.siliconflow.cn/v1")
    monkeypatch.setenv("LLM_EMBEDDINGS_KEY", "sk-emb")
    monkeypatch.setenv("LLM_EMBEDDINGS_MODEL", "BAAI/bge-m3")
    # Allow is_safe_http_url before pin (the test does not perform a real DNS pin).
    monkeypatch.setattr(llm_mod, "is_safe_http_url", lambda *a, **kw: True)

    llm = LLMClient(api_base="https://api.openai.com/v1", api_key="sk-chat", model="gpt-4o")
    import asyncio

    vecs = asyncio.run(llm.embed(["hello"]))
    assert vecs == [[0.1, 0.2, 0.3]]
    assert captured["url"].startswith("https://api.siliconflow.cn/v1/embeddings")


def test_llm_client_embed_falls_back_to_chat_base_when_no_override(monkeypatch) -> None:
    """When LLM_EMBEDDINGS_BASE is not configured, embed should fall back to LLM_API_BASE (unchanged behavior)."""
    captured: dict[str, Any] = {}

    class _StubResp:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {"data": [{"embedding": [0.0]}]}

        def raise_for_status(self) -> None:
            return None

    class _StubClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, **kw):
            captured["url"] = url
            return _StubResp()

    # embed has been split up: URL validation is in llm_client_ext, while request execution is in openai_transport.
    import realmock.platform.capabilities.ai.llm.client.llm_client_ext as llm_mod
    import realmock.platform.capabilities.ai.llm.client.openai_transport as ot_mod

    monkeypatch.setattr(ot_mod, "make_pinned_async_client", lambda *a, **kw: _StubClient())
    monkeypatch.setattr(llm_mod, "is_safe_http_url", lambda *a, **kw: True)
    get_settings.cache_clear()
    monkeypatch.delenv("LLM_EMBEDDINGS_BASE", raising=False)
    monkeypatch.delenv("LLM_EMBEDDINGS_KEY", raising=False)
    monkeypatch.delenv("LLM_EMBEDDINGS_MODEL", raising=False)
    monkeypatch.setenv("LLM_API_BASE", "https://api.deepseek.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-ds")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")

    llm = LLMClient(api_base="https://api.deepseek.com/v1", api_key="sk-ds", model="deepseek-chat")
    import asyncio

    asyncio.run(llm.embed(["hi"]))
    assert captured["url"].startswith("https://api.deepseek.com/v1/embeddings")


def test_llm_client_embed_decrypt_failure_fails_closed(monkeypatch, tmp_path) -> None:
    """An Embeddings key decryption failure must raise and abort; it must not fall back to sending a plaintext key."""
    import asyncio

    import realmock.platform.capabilities.ai.llm.client.llm_client_ext as llm_mod
    import realmock.platform.capabilities.ai.llm.client.openai_transport as ot_mod
    from realmock.platform.core import secrets as secrets_mod
    from realmock.platform.core.secrets import encrypt_secret

    # Use a fixed master plus an isolated keyfile (following the test_secrets.py precedent) to prevent tests from writing into the source tree.
    import base64 as _b64

    monkeypatch.setenv("SECRET_KEY", _b64.b64encode(b"a" * 32).decode())
    monkeypatch.setattr(secrets_mod, "_SHARED_DATA", tmp_path)
    monkeypatch.setattr(secrets_mod, "_DEFAULT_KEYFILE", tmp_path / ".secret.key")
    secrets_mod._reset_cache()
    try:
        requested: list[str] = []

        class _StubClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, **kw):
                requested.append(url)
                raise AssertionError("No requests should be sent")

        monkeypatch.setattr(ot_mod, "make_pinned_async_client", lambda *a, **kw: _StubClient())
        monkeypatch.setattr(llm_mod, "is_safe_http_url", lambda *a, **kw: True)
        # Tamper with enc:v2 ciphertext: encrypt with the same master, then modify one byte → decryption must fail.
        bad = encrypt_secret("sk-emb-valid") or ""
        _, rest = bad.split(":", 1)
        mangled = f"enc:v2:{rest[:-3]}xxx"
        broken_settings = _make_settings(llm_embeddings_key=mangled)
        # llm_client_ext.embed and openai_transport.embed_texts each read settings.
        monkeypatch.setattr(llm_mod, "get_settings", lambda: broken_settings)
        monkeypatch.setattr(ot_mod, "get_settings", lambda: broken_settings)

        llm = LLMClient(api_base="https://api.openai.com/v1", api_key="sk-chat", model="gpt-4o")
        with pytest.raises(ValueError):
            asyncio.run(llm.embed(["hello"], model="BAAI/bge-m3"))
        assert requested == [], "After decryption fails, do not fall back to sending a request with the plaintext key"
    finally:
        secrets_mod._reset_cache()
