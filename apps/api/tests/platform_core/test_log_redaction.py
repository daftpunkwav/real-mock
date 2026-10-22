# -*- coding: utf-8 -*-
"""Log-pipeline redaction regressions for a credential carried in a request URL.

A vendor that authenticates through query parameters (the Baidu OAuth token
endpoint puts ``client_secret`` there) makes the HTTP client log the secret:
the client logs the full request URL at INFO, and that record reaches the
application log. The redaction layer must therefore mask the query values of
every URL it emits, and the parameter names must stay so the request remains
diagnosable.

The same layer must also mask a credential that is quoted inside a sentence:
an upstream provider rejects a request with an error body that repeats the
credential it refused ("Incorrect API key provided: sk-..."), and that text
reaches the log as an argument or as the rendered exception.
"""

from __future__ import annotations

import io
import logging
import sys
from collections.abc import Callable

import httpx
import pytest

from realmock.platform.core.logging import RedactFilter, SafeFormatter
from realmock.platform.core.security import redact_log_template, redact_log_value

# The credential shape used by the Baidu ASR token request
# (``platform/capabilities/voice/stt/providers/baidu.py``).
_SECRET = "SuperSecretValue123"
_TOKEN_URL = (
    "https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials"
    f"&client_id=PUBLIC_ID&client_secret={_SECRET}"
)
# A fake provider key: the shape an upstream error body quotes back when it
# rejects the submitted credential.
_EMBEDDED_KEY = "sk-fakefakefakefake0123456789"


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

    def test_credential_quoted_inside_a_sentence_is_masked(self) -> None:
        """An upstream error body repeats the credential it refused.

        The whole-value heuristic cannot see a key inside a sentence, so the
        value is scanned token by token.
        """
        out = redact_log_value(f"Incorrect API key provided: {_EMBEDDED_KEY}")
        assert _EMBEDDED_KEY not in out
        assert "Incorrect API key provided" in out


class TestRedactLogTemplate:
    """A format template is a source literal: its text and its placeholders stay."""

    def test_long_words_of_the_template_are_not_rewritten(self) -> None:
        template = "record_round_finished failed sid=%s"
        assert redact_log_template(template) == template

    def test_placeholder_inside_a_url_survives(self) -> None:
        """Masking the query must not delete the ``%s`` of the template.

        A deleted placeholder leaves the argument count and the placeholder
        count out of balance, and the logging machinery then drops the line.
        """
        assert redact_log_template("url=https://example.com/?a=%s") == (
            "url=https://example.com/?a=%s"
        )

    def test_query_values_of_a_url_are_still_masked(self) -> None:
        out = redact_log_template(f"url={_TOKEN_URL} failed")
        assert _SECRET not in out
        assert "client_secret=***" in out


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

    def test_credential_quoted_in_an_argument_is_masked(self) -> None:
        """The upstream error body arrives as one argument and repeats the key."""

        def make_record() -> logging.LogRecord:
            return logging.LogRecord(
                name="realmock.voice",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="provider request failed: %s",
                args=(f"Incorrect API key provided: {_EMBEDDED_KEY}",),
                exc_info=None,
            )

        line = _emit(make_record)
        assert _EMBEDDED_KEY not in line
        assert "Incorrect API key provided" in line

    def test_credential_quoted_in_the_exception_text_is_masked(self) -> None:
        """The rendered exception text is a runtime value like any other."""
        try:
            raise RuntimeError(f"Incorrect API key provided: {_EMBEDDED_KEY}")
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
        assert _EMBEDDED_KEY not in line

    def test_a_template_keeps_its_placeholders_and_the_line_is_emitted(self) -> None:
        """A URL in a template must not cost the line its placeholder.

        The URL masking rewrites the query values; a ``%s`` among them has
        to survive, otherwise the argument count and the placeholder count
        diverge and the logging machinery drops the whole line.
        """

        def make_record() -> logging.LogRecord:
            return logging.LogRecord(
                name="realmock.core",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="url=https://example.com/?a=%s",
                args=("value",),
                exc_info=None,
            )

        line = _emit(make_record)
        assert "url=https://example.com/?a=value" in line


class TestConfiguredPipeline:
    """The application pipeline must actually install the redaction filter.

    The filter and the formatter work in isolation, but the credential only
    stays out of the log if the root handler runs the filter: a pipeline that
    drops the filter would ship the vendor secret in cleartext while every
    unit test above still passes.
    """

    @pytest.fixture
    def _root_logger_state(self):
        """Restore the root logger and the uvicorn loggers after the test."""
        root = logging.getLogger()
        saved = (
            list(root.handlers),
            root.level,
            {
                name: (logging.getLogger(name).handlers, logging.getLogger(name).propagate)
                for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
            },
        )
        yield
        root.handlers = saved[0]
        root.setLevel(saved[1])
        for name, (handlers, propagate) in saved[2].items():
            lg = logging.getLogger(name)
            lg.handlers = handlers
            lg.propagate = propagate

    def test_configure_logging_installs_the_redaction_filter(self, _root_logger_state) -> None:
        from realmock.platform.core.logging import configure_logging

        configure_logging()
        root = logging.getLogger()
        handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
        assert handlers, "configure_logging installed no stream handler on the root logger"
        assert any(isinstance(f, RedactFilter) for h in handlers for f in h.filters), (
            "the root handler runs no redaction filter: logged credentials "
            "would reach the log in cleartext"
        )

    def test_configured_pipeline_masks_a_query_credential(self, _root_logger_state) -> None:
        from realmock.platform.core.logging import configure_logging

        configure_logging()
        root = logging.getLogger()
        handler = next(h for h in root.handlers if isinstance(h, logging.StreamHandler))
        buffer = io.StringIO()
        handler.setStream(buffer)

        # The URL carries a test credential on purpose: the assertion below
        # states that the installed pipeline masks it before the line reaches
        # the log. The record goes through the handler the way the application
        # emits it, so the filter and the formatter both run.
        record = logging.LogRecord(
            name="realmock.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="provider request failed: %s",
            args=(_TOKEN_URL,),
            exc_info=None,
        )
        handler.handle(record)

        line = buffer.getvalue()
        assert line, "the configured pipeline emitted nothing"
        assert _SECRET not in line
        assert "client_secret=***" in line
