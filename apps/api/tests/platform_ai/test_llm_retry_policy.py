"""Unit tests for the shared LLM retry policy (retry_policy.py).

Covers: the doubled-pair delay ladder and its bounds, Retry-After parsing
(delta-seconds, HTTP-date, garbage) and its cap, and the retryable
status/exception classifiers (ReadTimeout is deliberately never retryable).
"""

from __future__ import annotations

import datetime as dt
from email.utils import format_datetime

import httpx

from realmock.platform.capabilities.ai.llm.retry_policy import (
    MAX_RETRY_AFTER_SECONDS,
    RETRY_DELAYS,
    is_retryable_exception,
    is_retryable_status,
    parse_retry_after,
    retry_delay,
)


def test_retry_delay_follows_ladder_and_clamps() -> None:
    assert RETRY_DELAYS == (10, 10, 20, 20, 40, 40, 80, 80, 100, 100)
    assert retry_delay(0) == 10
    assert retry_delay(2) == 20
    assert retry_delay(9) == 100
    # Out-of-range attempts hold the last rung instead of growing unbounded.
    assert retry_delay(99) == 100
    assert retry_delay(-1) == 100


def test_retry_after_overrides_ladder_and_is_capped() -> None:
    assert retry_delay(0, retry_after=7.5) == 7.5
    # Non-positive Retry-After falls back to the ladder.
    assert retry_delay(2, retry_after=0) == 20
    assert retry_delay(2, retry_after=-5) == 20
    # A hostile header cannot stall a turn for minutes.
    assert retry_delay(0, retry_after=999_999) == MAX_RETRY_AFTER_SECONDS


def test_parse_retry_after_delta_seconds_and_absent() -> None:
    assert parse_retry_after({"retry-after": "12"}) == 12.0
    assert parse_retry_after({"retry-after": " 3 "}) == 3.0
    assert parse_retry_after({}) is None
    assert parse_retry_after({"retry-after": ""}) is None
    assert parse_retry_after(None) is None


def test_parse_retry_after_http_date() -> None:
    target = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=60)
    header = format_datetime(target, usegmt=True)
    value = parse_retry_after({"retry-after": header})
    assert value is not None
    assert 0 < value <= 60


def test_parse_retry_after_garbage_is_none() -> None:
    assert parse_retry_after({"retry-after": "soon"}) is None


def test_is_retryable_status() -> None:
    assert is_retryable_status(429)
    assert is_retryable_status(500)
    assert is_retryable_status(503)
    assert not is_retryable_status(400)
    assert not is_retryable_status(401)
    assert not is_retryable_status(404)


def test_is_retryable_exception_excludes_read_timeout() -> None:
    assert is_retryable_exception(httpx.ConnectError("down"))
    assert is_retryable_exception(httpx.WriteError("w"))
    assert is_retryable_exception(httpx.RemoteProtocolError("p"))
    # A read timeout means the provider is still generating; retrying would
    # multiply an already-minutes-scale wait.
    assert not is_retryable_exception(httpx.ReadTimeout("still generating"))
    assert not is_retryable_exception(ValueError("unrelated"))
