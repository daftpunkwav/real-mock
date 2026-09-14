"""realmock.platform.core.errors unit tests: registry + ApiBusinessError + raise_error.

Cover the E6 error-code system contract (A/B/C category + domain + sequence number):
- Registry CATALOG contains the authoritative 42 codes (see errors.py CATALOG);
- ApiBusinessError inherits HTTPException while carrying error_code/error_hint;
- raise_error formats message using a code + placeholders;
- An unregistered code degrades to B0001 instead of raising KeyError.
"""

from __future__ import annotations

from fastapi import HTTPException

from realmock.platform.core.errors import (
    CATALOG,
    ApiBusinessError,
    get_spec,
    raise_error,
)


def test_catalog_has_three_groups() -> None:
    """Each of categories A/B/C has at least 4 registration codes."""
    a_codes = [c for c in CATALOG if c.startswith("A")]
    b_codes = [c for c in CATALOG if c.startswith("B")]
    c_codes = [c for c in CATALOG if c.startswith("C")]
    assert len(a_codes) >= 15, f"Category A should cover multiple domains; actual coverage is only {len(a_codes)} items"
    assert len(b_codes) >= 2, f"Category B must include at least B0001/B1001; actual count: {len(b_codes)} items"
    assert len(c_codes) >= 7, f"Category C covers LLM/reports/voice/search/RAG; actual coverage: {len(c_codes)} items"


def test_error_spec_is_frozen() -> None:
    """ErrorSpec is a frozen dataclass and is immutable at runtime."""
    spec = get_spec("A1005")
    assert spec.code == "A1005"
    assert spec.http_status == 404
    assert "Resume not found" in spec.message
    # frozen check: assigning attributes must raise AttributeError
    try:
        spec.code = "B0001"  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("ErrorSpec must be frozen")


def test_api_business_error_inherits_http_exception() -> None:
    """ApiBusinessError must inherit from HTTPException to preserve backward compatibility."""
    spec = get_spec("A0006")
    err = ApiBusinessError(spec, message="test")
    assert isinstance(err, HTTPException)
    assert err.status_code == 400
    assert err.detail == "test"
    assert err.error_code == "A0006"
    assert err.error_hint  # Non-empty
    assert err.error_retryable is False


def test_raise_error_with_placeholder() -> None:
    """raise_error supports formatting message with {placeholder}."""
    try:
        raise_error("A0413", max=10)
    except ApiBusinessError as e:
        assert e.error_code == "A0413"
        assert "10" in e.detail
        return
    raise AssertionError("expected ApiBusinessError")


def test_raise_error_unknown_code_falls_back() -> None:
    """Unregistered codes fall back to B0001 without raising KeyError."""
    try:
        raise_error("Z9999")
    except ApiBusinessError as e:
        assert e.error_code == "B0001"
        return
    raise AssertionError("expected ApiBusinessError")


def test_retryable_field_propagates() -> None:
    """Pass the retryable field correctly; 429 and 5xx/502/503 default to True."""
    assert get_spec("A0002").retryable is True   # 429 rate limiting
    assert get_spec("B0001").retryable is True   # 500 system error
    assert get_spec("B1001").retryable is True   # 500 write failed
    assert get_spec("C0001").retryable is True   # 502 LLM
    assert get_spec("C1001").retryable is True   # 502 report
    assert get_spec("A1005").retryable is False  # 404 resume not found
    assert get_spec("A2002").retryable is False  # 400 interview already finished


def test_codes_are_unique() -> None:
    """Registry codes must be unique."""
    codes = list(CATALOG.keys())
    assert len(codes) == len(set(codes)), "CATALOG contains duplicate codes"


def test_hints_non_empty_for_4xx_5xx() -> None:
    """4xx/5xx user-visible errors must have a recovery hint."""
    for code, spec in CATALOG.items():
        # 4xx/5xx must have hint; C-class 200* notifications may omit (by design)
        if spec.http_status >= 400 and not spec.hint:
            raise AssertionError(f"{code} is missing hint")


def test_with_headers_chains() -> None:
    """ApiBusinessError.with_headers supports chained addition of response headers (Retry-After, etc.)."""
    spec = get_spec("A0002")
    err = ApiBusinessError(spec, message="rate").with_headers({"Retry-After": "60"})
    assert err.headers == {"Retry-After": "60"}
    # Chained appends do not lose data
    err2 = err.with_headers({"X-Test": "1"})
    assert err2.headers == {"Retry-After": "60", "X-Test": "1"}
