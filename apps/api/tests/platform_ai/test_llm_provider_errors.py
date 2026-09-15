"""Provider error tests for apps/api/src/realmock/platform/capabilities/ai/llm/provider_errors.py.

Covers: _response_status/_response_text extraction variants and is_context_overflow
code/status gating including never-raises guarantee.

Conventions: pure functions, no network; asyncio_mode=auto.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from realmock.platform.capabilities.ai.llm import provider_errors as pe_mod
from realmock.platform.capabilities.ai.llm.provider_errors import is_context_overflow



def _exc_with(status: Any, text: str = "", payload: Any = None, *, raw_json: Any = None) -> Exception:
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    if raw_json is not None:
        resp.json = raw_json
    else:
        resp.json = MagicMock(return_value=payload, side_effect=None if payload is not None else Exception("no"))
    exc = ValueError("boom")
    exc.response = resp  # type: ignore[attr-defined]
    return exc


def test_response_status_variants() -> None:
    assert pe_mod._response_status(_exc_with(400)) == 400
    assert pe_mod._response_status(ValueError("no resp")) is None
    assert pe_mod._response_status(_exc_with(None)) is None
    assert pe_mod._response_status(_exc_with("bad")) is None


def test_response_text_variants() -> None:
    assert pe_mod._response_text(_exc_with(400, text="hello")) == "hello"
    assert pe_mod._response_text(_exc_with(400, payload={"code": "x"})) == "{'code': 'x'}"
    assert pe_mod._response_text(_exc_with(400)) == ""
    assert pe_mod._response_text(_exc_with(400, raw_json="not-callable")) == ""
    assert pe_mod._response_text(ValueError("none")) == ""


def test_is_context_overflow_codes_and_status_gate() -> None:
    assert is_context_overflow(ValueError("context_length_exceeded")) is True
    assert is_context_overflow(_exc_with(400, text="Maximum context length reached")) is True
    assert is_context_overflow(_exc_with(413, text="input too long for model")) is True
    assert is_context_overflow(_exc_with(400, text="too many tokens in request")) is True
    assert is_context_overflow(_exc_with(400, text="exceeds the model's maximum")) is True
    assert is_context_overflow(_exc_with(400, text="plain bad request")) is False
    assert is_context_overflow(_exc_with(401, text="Maximum context length reached")) is False
    assert is_context_overflow(ValueError("auth failed")) is False


def test_is_context_overflow_never_raises() -> None:
    class _BadStr(Exception):
        def __str__(self) -> str:
            raise RuntimeError("no str")

    assert is_context_overflow(_BadStr()) is False
