"""Agent error log: opt-in JSONL persistence for tool/loop failures."""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from realmock.platform.capabilities.ai.agent.tools.executor import invoke_with_timeout
from realmock.platform.core.agent_error_log import FLAG_ENV, PATH_ENV, log_agent_error


class _TimeoutBundle:
    async def execute(self, name: str, args: dict) -> str:
        del name, args
        raise asyncio.TimeoutError


class _OkBundle:
    async def execute(self, name: str, args: dict) -> str:
        del name, args
        return "fine"


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path, *, enabled: bool) -> str:
    target = str(tmp_path / "agent_errors.log")
    if enabled:
        monkeypatch.setenv(FLAG_ENV, "1")
    else:
        monkeypatch.delenv(FLAG_ENV, raising=False)
    monkeypatch.setenv(PATH_ENV, target)
    return target


def test_disabled_by_default_writes_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    target = _env(monkeypatch, tmp_path, enabled=False)
    log_agent_error(domain="resume", tool="web_search", kind="timeout", message="x")
    assert not os.path.exists(target)


def test_enabled_timeout_is_persisted(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    target = _env(monkeypatch, tmp_path, enabled=True)
    raw, status = asyncio.run(
        invoke_with_timeout(
            _TimeoutBundle(),  # type: ignore[arg-type]
            "web_search",
            {},
            timeout=5,
            context={"domain": "resume", "session": "7"},
        )
    )
    assert status == "error"
    assert json.loads(raw)["error"] == "timeout"
    with open(target, encoding="utf-8") as handle:
        record = json.loads(handle.read().strip().splitlines()[-1])
    assert record["domain"] == "resume"
    assert record["session"] == "7"
    assert record["tool"] == "web_search"
    assert record["kind"] == "timeout"


def test_success_writes_nothing(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    target = _env(monkeypatch, tmp_path, enabled=True)
    raw, status = asyncio.run(
        invoke_with_timeout(_OkBundle(), "web_search", {}, timeout=5)  # type: ignore[arg-type]
    )
    assert (raw, status) == ("fine", "done")
    assert not os.path.exists(target)


def test_log_never_raises(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv(FLAG_ENV, "1")
    # A directory is not writable as a file: must be swallowed, not raised.
    monkeypatch.setenv(PATH_ENV, str(tmp_path))
    log_agent_error(tool="t", kind="k", message="m")
    # The failed write left no artifacts behind.
    assert tmp_path.is_dir()
    assert list(tmp_path.iterdir()) == []


def test_enabled_tool_failure_masks_embedded_credential(
    monkeypatch: pytest.MonkeyPatch, tmp_path, caplog
) -> None:
    """A provider error quoting the rejected key must not reach any sink raw.

    The observation, the persisted error record, and the log message all
    carry the exception text, so all three are redacted at the funnel; the
    traceback stays attached to the log record for the configured pipeline
    (SafeFormatter) to scrub.
    """

    class _BoomBundle:
        async def execute(self, name: str, args: dict) -> str:
            del name, args
            raise RuntimeError(
                "provider 401: Incorrect API key provided: sk-proj-abcdefghij123456789"
            )

    target = _env(monkeypatch, tmp_path, enabled=True)
    raw, status = asyncio.run(
        invoke_with_timeout(_BoomBundle(), "web_search", {"q": "x"}, timeout=5)  # type: ignore[arg-type]
    )
    assert status == "error"
    assert "sk-proj-abcdefghij123456789" not in raw
    with open(target, encoding="utf-8") as handle:
        persisted = json.loads(handle.readlines()[-1])
    assert "sk-proj-abcdefghij123456789" not in persisted["message"]
    # The warning's message argument is the sanitized string: if the funnel
    # ever passes the raw exception again, the rendered log line would carry
    # the credential even though this file's other sinks stay clean.
    tool_records = [
        record for record in caplog.records if "Agent tool failed" in record.getMessage()
    ]
    assert tool_records, "the executor emitted no failure warning"
    assert "sk-proj-abcdefghij123456789" not in tool_records[0].getMessage()


def test_error_observation_redacts_credential_in_args(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The argument echo in an error observation is scanned like any text.

    The model's own arguments can carry a credential (a URL with a key in
    the query); the echo returns to the model inside the observation.
    """

    class _BoomBundle:
        async def execute(self, name: str, args: dict) -> str:
            del name
            raise RuntimeError("boom")

    _env(monkeypatch, tmp_path, enabled=True)
    raw, status = asyncio.run(
        invoke_with_timeout(
            _BoomBundle(),  # type: ignore[arg-type]
            "web_fetch",
            {"url": "https://api.vendor.com/v1?api_key=SuperSecretValue123"},
            timeout=5,
        )
    )
    assert status == "error"
    assert "SuperSecretValue123" not in raw
    assert "api_key=***" in raw
