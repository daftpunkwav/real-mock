"""Structured logging and sensitive-field redaction.

- :class:`SafeFormatter`: emits JSON-style output by default, including trace_id;
- :class:`RedactFilter`: automatically replaces API Keys / Authorization headers in logs;
- :func:`configure_logging`: installs logging once during FastAPI lifespan startup.

Redaction covers ``record.msg`` and ``record.args`` while redacting **only their string components**,
without changing the count or order of formatting placeholders such as `%s/%d`—a contract required
by the logger's formatting phase.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import uuid
from typing import Any

from realmock.platform.core.security import redact_api_key as _redact

# Request-level trace_id, which facilitates stringing together logs of the same request
_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default=""
)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def set_trace_id(value: str | None = None) -> contextvars.Token:
    """Set the current trace_id and return a ``Token`` (paired with :func:`reset_trace_id`).

    When ``value`` is omitted, generate a new uuid4. Return a Token rather than str so middleware
    can reset it in finally and prevent cross-request contamination.
    """
    return _trace_id_var.set(value or new_trace_id())


def get_trace_id() -> str:
    return _trace_id_var.get()


def reset_trace_id(token) -> None:
    """Restore the ContextVar; use it together with :func:`set_trace_id` (middleware context)."""
    _trace_id_var.reset(token)


# The API Key/Bearer token in the log is automatically desensitized.
# Reuse the canonical :func:`realmock.platform.core.security.redact_api_key` entry point to prevent regex drift between two implementations.


class RedactFilter(logging.Filter):
    """Redact sensitive fields before log output.

    Strategy:

    - Call :func:`redact_api_key` only for **string** values in ``record.msg`` (template) and
      ``record.args`` (arguments);
    - Preserve non-string arguments (such as numbers, bytes, Exception, etc.) unchanged, without disrupting
      the number of ``%s/%d`` placeholders;
    - Also redact ``record.exc_text`` (formatted exception stack text) to prevent
      leakage from strings containing Keys thrown by an upstream LLM/SDK.

    Supporting a new Key format requires changes only in :func:`redact_api_key`.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = _redact(record.msg)
            if record.args:
                new_args: list[Any] = []
                for a in record.args:
                    if isinstance(a, str):
                        new_args.append(_redact(a))
                    else:
                        new_args.append(a)
                record.args = tuple(new_args)
            exc_text = getattr(record, "exc_text", None)
            if isinstance(exc_text, str):
                record.exc_text = _redact(exc_text)
        except Exception:  # pragma: no cover - fail open
            # Intentionally silent and cannot be changed to log: this filter runs in the logging pipeline,
            # Posting logs here again will enter this filter again, causing recursion; if desensitization fails, the original
            # Records have documented fail-open semantics
            pass
        return True


class SafeFormatter(logging.Formatter):
    """JSON structured output + embedded trace_id."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "trace_id": get_trace_id(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    """Replace the default handler and install a redaction filter.

    All environments emit structured JSON logs (including trace_id), allowing local troubleshooting
    and log collectors (Loki / ES) to use the same format.
    """
    root = logging.getLogger()
    # Clear uvicorn/default installation
    for h in list(root.handlers):
        root.removeHandler(h)

    stream = logging.StreamHandler(stream=sys.stdout)
    stream.setLevel(level)
    stream.addFilter(RedactFilter())
    stream.setFormatter(SafeFormatter())
    root.addHandler(stream)
    root.setLevel(level)

    # uvicorn's own logs inherit the same format
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
