"""OpenAI transport tests for apps/api/src/realmock/platform/capabilities/ai/llm/client/openai_transport.py.

Covers: build_payload optionals, chat_completions_headers, strip_code_fences,
repair_common_json_errors, chat_completions success/redacted-error paths and
embed_texts settings/key/decrypt/error branches.

Conventions: no real network (httpx/pinned client mocked); asyncio_mode=auto.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from realmock.platform.capabilities.ai.llm.client import openai_transport as ot_mod
from realmock.platform.capabilities.ai.llm.client.openai_transport import (
    build_payload,
    chat_completions_headers,
    repair_common_json_errors,
    strip_code_fences,
)
from realmock.platform.core.secrets import LegacySecretFormatError



def _pinned(http: MagicMock) -> MagicMock:
    pinned = MagicMock()
    pinned.__aenter__ = AsyncMock(return_value=http)
    pinned.__aexit__ = AsyncMock(return_value=False)
    return pinned


def _ok_resp(payload: Any) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.request = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


def _err_resp(status: int) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.request = MagicMock()
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(str(status), request=MagicMock(), response=resp)
    )
    return resp


def _patch_net(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ot_mod, "_is_local_allowed", lambda: False)
    monkeypatch.setattr(ot_mod, "_require_https", lambda: False)


def test_build_payload_optionals() -> None:
    p = build_payload("m", [], 0.5, 64, "max",
                      response_format={"type": "json_object"}, tools=[{"t": 1}])
    assert p["response_format"] == {"type": "json_object"}
    assert p["tools"] == [{"t": 1}]
    assert p["reasoning_effort"] == "high"
    p2 = build_payload("m", [], 0.5, 64, "low")
    assert p2["reasoning_effort"] == "low"
    p3 = build_payload("m", [], 0.5, 64, None)
    assert "reasoning_effort" not in p3
    assert chat_completions_headers("k") == {
        "Authorization": "Bearer k", "Content-Type": "application/json",
    }


def test_strip_code_fences_variants() -> None:
    assert strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_code_fences('```\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_code_fences('{"a": 1}') == '{"a": 1}'
    assert strip_code_fences('```json\n{"a": 1}') == '{"a": 1}'


def test_repair_common_json_errors() -> None:
    assert json.loads(repair_common_json_errors('{"a": 1,}')) == {"a": 1}
    assert json.loads(repair_common_json_errors('[1, 2,]')) == [1, 2]
    assert json.loads(repair_common_json_errors('{"a": 1, "b": 2}')) == {"a": 1, "b": 2}
    raw = '{"a": "x\ny\tz\rr", "q": "he\\"s", "n": 1,}'
    assert json.loads(repair_common_json_errors(raw)) == {"a": "x\ny\tz\rr", "q": 'he"s', "n": 1}


@pytest.mark.asyncio
async def test_chat_completions_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_net(monkeypatch)
    http = MagicMock()
    http.post = AsyncMock(return_value=_ok_resp({"choices": []}))
    with patch.object(ot_mod, "make_pinned_async_client", return_value=_pinned(http)):
        out = await ot_mod.chat_completions(
            api_base="https://x", api_key="k", url="https://x/chat",
            payload={"model": "m"}, timeout=5.0, log_label="t", model="m",
        )
    assert out == {"choices": []}
    _, kwargs = http.post.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer k"


@pytest.mark.asyncio
async def test_chat_completions_http_error_redacts_key(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _patch_net(monkeypatch)
    http = MagicMock()
    with (
        patch.object(ot_mod, "make_pinned_async_client", return_value=_pinned(http)),
        patch.object(ot_mod, "_retry_request", new=AsyncMock(return_value=_err_resp(500))),
        caplog.at_level("WARNING"),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await ot_mod.chat_completions(
            api_base="https://x", api_key="sk-secret-xyz-123", url="https://x/chat",
            payload={}, timeout=5.0, log_label="t", model="m",
        )
    assert not any("sk-secret-xyz-123" in r.getMessage() for r in caplog.records)


def _embed_settings(**kw: Any) -> SimpleNamespace:
    base = {"effective_embeddings_base": "https://emb", "effective_embeddings_model": "em",
            "effective_embeddings_key": "emb-key"}
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_embed_texts_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_net(monkeypatch)
    monkeypatch.setattr(ot_mod, "get_settings", lambda: _embed_settings())
    monkeypatch.setattr(ot_mod, "decrypt_secret", lambda v: v)
    http = MagicMock()
    http.post = AsyncMock(return_value=_ok_resp({"data": [{"embedding": [0.1, 0.2]}]}))
    with patch.object(ot_mod, "make_pinned_async_client", return_value=_pinned(http)):
        out = await ot_mod.embed_texts(texts=["hi"], model="", api_base="https://x", api_key="k")
    assert out == [[0.1, 0.2]]
    args, kwargs = http.post.call_args
    assert args[0] == "https://emb/embeddings"
    assert kwargs["headers"]["Authorization"] == "Bearer emb-key"
    assert kwargs["json"]["model"] == "em"


@pytest.mark.asyncio
async def test_embed_texts_falls_back_to_llm_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_net(monkeypatch)
    monkeypatch.setattr(ot_mod, "get_settings", lambda: _embed_settings(effective_embeddings_key=""))
    monkeypatch.setattr(ot_mod, "decrypt_secret", lambda v: ("DEC:" + v) if v else None)
    http = MagicMock()
    http.post = AsyncMock(return_value=_ok_resp({"data": []}))
    with patch.object(ot_mod, "make_pinned_async_client", return_value=_pinned(http)):
        assert await ot_mod.embed_texts(texts=["hi"], model="m2", api_base="x", api_key="sk-x") == []
    _, kwargs = http.post.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer DEC:sk-x"
    assert kwargs["json"]["model"] == "m2"


@pytest.mark.asyncio
async def test_embed_texts_decrypt_errors_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_net(monkeypatch)
    monkeypatch.setattr(ot_mod, "get_settings", lambda: _embed_settings())
    monkeypatch.setattr(
        ot_mod, "decrypt_secret",
        MagicMock(side_effect=LegacySecretFormatError("old")),
    )
    with pytest.raises(LegacySecretFormatError):
        await ot_mod.embed_texts(texts=["hi"], model="m", api_base="x", api_key="k")
    monkeypatch.setattr(ot_mod, "decrypt_secret", MagicMock(side_effect=ValueError("bad")))
    with pytest.raises(ValueError):
        await ot_mod.embed_texts(texts=["hi"], model="m", api_base="x", api_key="k")


@pytest.mark.asyncio
async def test_embed_texts_http_error_redacts_key(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _patch_net(monkeypatch)
    monkeypatch.setattr(
        ot_mod, "get_settings",
        lambda: _embed_settings(effective_embeddings_key="sk-embed-secret-99"),
    )
    monkeypatch.setattr(ot_mod, "decrypt_secret", lambda v: v)
    http = MagicMock()
    with (
        patch.object(ot_mod, "make_pinned_async_client", return_value=_pinned(http)),
        patch.object(ot_mod, "_retry_request", new=AsyncMock(return_value=_err_resp(500))),
        caplog.at_level("WARNING"),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await ot_mod.embed_texts(texts=["hi"], model="m", api_base="x", api_key="k")
    assert not any("sk-embed-secret-99" in r.getMessage() for r in caplog.records)


def test_build_payload_extra_body_overrides_standard_keys():
    payload = build_payload(
        "m", [{"role": "user", "content": "hi"}], 0.7, 100, None,
        extra_body={"temperature": 0.9, "vendor_field": {"deep": 1}},
    )
    assert payload["temperature"] == 0.9  # override wins
    assert payload["vendor_field"] == {"deep": 1}
    assert payload["model"] == "m" and payload["stream"] is False


def test_build_payload_without_extra_body_is_unchanged():
    payload = build_payload("m", [], 0.7, 100, None)
    assert "vendor_field" not in payload


def test_chat_completions_headers_extra_merge():
    headers = chat_completions_headers("k", {"X-Custom": "v"})
    assert headers["Authorization"] == "Bearer k"
    assert headers["X-Custom"] == "v"
    # No extra_headers: only the standard keys are present.
    bare = chat_completions_headers("k")
    assert set(bare) == {"Authorization", "Content-Type"}


def test_llm_client_carries_extra_body_and_headers_into_payload():
    from realmock.platform.capabilities.ai.llm.client.llm_client import LLMClient

    client = LLMClient(
        api_base="https://api.example.com", api_key="k", model="m",
        extra_body={"temperature": 0.3}, extra_headers={"X-Region": "cn"},
    )
    payload = client._build_payload([{"role": "user", "content": "hi"}], 0.7)
    assert payload["temperature"] == 0.3
    assert client.extra_headers == {"X-Region": "cn"}


def test_unified_client_extra_headers_survive_protocol_delegation():
    """extras.extra_headers must reach non-openai_chat protocols too (UnifiedLLMClient)."""
    from realmock.platform.capabilities.ai.llm.client.llm_client import LLMClient
    from realmock.platform.capabilities.ai.llm.client.protocol_utils import _headers
    from realmock.platform.capabilities.ai.llm.client.unified_client import UnifiedLLMClient

    headers = _headers(
        "k", "anthropic_messages", {"X-Custom": "v", "anthropic-version": "2024-01-01"}
    )
    assert headers["x-api-key"] == "k"
    assert headers["anthropic-version"] == "2024-01-01"  # extra wins over standard
    assert headers["X-Custom"] == "v"

    unified = UnifiedLLMClient.from_stage_config(
        {
            "api_base": "https://api.example.com",
            "api_key": "k",
            "model": "m",
            "protocol": "anthropic_messages",
            "extras": {
                "extra_body": {"max_tokens": 999},
                "extra_headers": {"X-Custom": "v"},
            },
        }
    )
    assert unified.extra_headers == {"X-Custom": "v"}
    url, payload = unified._build_url_and_payload([{"role": "user", "content": "hi"}])
    assert payload["max_tokens"] == 999  # extra_body wins over protocol translation

    client = LLMClient(
        api_base="https://api.example.com", api_key="k", model="m",
        protocol="anthropic_messages",
        extra_body={"max_tokens": 999}, extra_headers={"X-Custom": "v"},
    )
    delegated = client._delegate()
    assert delegated.extra_headers == {"X-Custom": "v"}
    assert delegated.extra_body == {"max_tokens": 999}
