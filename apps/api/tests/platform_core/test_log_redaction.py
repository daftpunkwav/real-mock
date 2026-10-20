# -*- coding: utf-8 -*-
"""Log-pipeline redaction regressions for a credential carried in a request URL.

A vendor that authenticates through query parameters (the Baidu OAuth token
endpoint puts ``client_secret`` there) makes the HTTP client log the secret:
the client logs the full request URL at INFO, and that record reaches the
application log. The redaction layer must therefore mask the query values of
every URL it emits, and the parameter names must stay so the request remains
diagnosable.
"""

from __future__ import annotations

import io
import logging
import sys
from collections.abc import Callable

import httpx

from realmock.platform.core.logging import RedactFilter, SafeFormatter
from realmock.platform.core.security import redact_log_value

# The credential shape used by the Baidu ASR token request
# (``platform/capabilities/voice/stt/providers/baidu.py``).
_SECRET = "SuperSecretValue123"
_TOKEN_URL = (
    "https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials"
    f"&client_id=PUBLIC_ID&client_secret={_SECRET}"
)


def _emit(record_factory: Callable[[], logging.LogRecord]) -> str:
    """Format one record through the app's filter + formatter and return the line."""
    handler = logging.StreamHandler(io.StringIO())
    handler.addFilter(RedactFilter())
    handler.setFormatter(SafeFormatter())
    record = record_factory()
    handler.filter(record)
    return handler.format(record)


class TestRedactLogValue:
    def test_query_values_are_masked_and_names_kept(self) -> None:
        out = redact_log_value(_TOKEN_URL)
        assert _SECRET not in out
        assert "client_secret=***" in out
        assert "grant_type=***" in out
        assert "aip.baidubce.com/oauth/2.0/token" in out

    def test_url_without_query_is_unchanged(self) -> None:
        url = "https://api.example.com/v1/chat/completions"
        assert redact_log_value(url) == url

    def test_userinfo_password_is_masked(self) -> None:
        out = redact_log_value("https://user:hunter2@api.example.com/v1")
        assert "hunter2" not in out
        assert "user:***@api.example.com" in out

    def test_prose_around_the_url_is_preserved(self) -> None:
        out = redact_log_value(f"request to {_TOKEN_URL} failed")
        assert _SECRET not in out
        assert out.startswith("request to https://aip.baidubce.com/oauth/2.0/token?")
        assert out.endswith(" failed")

    def test_bare_key_outside_a_url_is_still_masked(self) -> None:
        assert redact_log_value("sk-abc123def456ghi789") == "sk-a***i789"

    def test_empty_value_returns_empty(self) -> None:
        assert redact_log_value("") == ""
        assert redact_log_value(None) == ""


class TestLogPipeline:
    def test_url_argument_is_masked(self) -> None:
        """The HTTP client logs the request URL as a URL object, not as text."""

        def make_record() -> logging.LogRecord:
            return logging.LogRecord(
                name="httpx",
                level=logging.INFO,
                pathname=__file__,
                lineno=1,
                msg='HTTP Request: %s %s "%s %d %s"',
                args=("GET", httpx.URL(_TOKEN_URL), "HTTP/1.1", 200, "OK"),
                exc_info=None,
            )

        line = _emit(make_record)
        assert _SECRET not in line
        assert "client_secret=***" in line

    def test_url_inside_a_message_is_masked(self) -> None:
        def make_record() -> logging.LogRecord:
            return logging.LogRecord(
                name="realmock.voice",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="provider request failed: %s",
                args=(_TOKEN_URL,),
                exc_info=None,
            )

        line = _emit(make_record)
        assert _SECRET not in line
        assert "client_secret=***" in line

    def test_url_inside_the_exception_text_is_masked(self) -> None:
        try:
            raise RuntimeError(f"URL denied by policy: {_TOKEN_URL!r}")
        except RuntimeError:
            exc_info = sys.exc_info()

        def make_record() -> logging.LogRecord:
            return logging.LogRecord(
                name="realmock.core",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="provider call failed",
                args=(),
                exc_info=exc_info,
            )

        line = _emit(make_record)
        assert _SECRET not in line
        assert "client_secret=***" in line
