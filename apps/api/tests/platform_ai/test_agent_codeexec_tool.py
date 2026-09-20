"""Code-exec tool tests for apps/api/src/realmock/platform/capabilities/ai/agent/tools/codeexec.py.

Covers: _kill_tree POSIX/dead paths, timeout clamping, missing node runtime,
misconfigured isolation, overlong code, launch OSError, suffix/observation formatting.

Conventions: no real network (runtimes/backends mocked); asyncio_mode=auto.
"""

from __future__ import annotations

import pytest

import realmock.platform.capabilities.ai.agent.tools.codeexec as ce



@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()


def test_kill_tree_posix_and_dead(monkeypatch) -> None:
    class _P:
        pid = 12345
        killed = False

        def kill(self):
            self.killed = True

    # POSIX killpg success path (create attr on Windows).
    monkeypatch.setattr(ce.os, "name", "posix")
    monkeypatch.setattr(ce.os, "killpg", lambda pid, sig: None, raising=False)
    import signal as _sig

    monkeypatch.setattr(_sig, "SIGKILL", 9, raising=False)
    p = _P()
    ce._kill_tree(p)  # type: ignore[arg-type]
    assert p.killed is False
    # POSIX killpg raises -> falls back to proc.kill.
    def _boom(pid, sig):
        raise ProcessLookupError("gone")

    monkeypatch.setattr(ce.os, "killpg", _boom, raising=False)
    ce._kill_tree(p)  # type: ignore[arg-type]
    assert p.killed is True
    # proc.kill raises -> swallowed.
    class _Dead:
        pid = 1

        def kill(self):
            raise ProcessLookupError("gone")

    ce._kill_tree(_Dead())  # type: ignore[arg-type]


def test_run_code_timeout_clamp_and_bad_timeout(monkeypatch) -> None:
    # timeout=0 clamps to min; bad timeout string falls back to default.
    r = ce.run_code_snippet("python", "print(1)", timeout=0, isolation="process")
    assert r.exit_code == 0
    assert "1" in r.stdout
    r2 = ce.run_code_snippet("python", "print(1)", timeout="bad", isolation="process")  # type: ignore[arg-type]
    assert r2.exit_code == 0


def test_run_code_nonfinite_timeout_falls_back_to_default() -> None:
    # NaN/inf must not escape the never-raise API (they poison child waits).
    r = ce.run_code_snippet("python", "print(1)", timeout=float("nan"), isolation="process")
    assert r.error == "" and r.exit_code == 0
    r2 = ce.run_code_snippet("python", "print(1)", timeout=float("inf"), isolation="process")
    assert r2.error == "" and r2.exit_code == 0


def test_node_missing_returns_error(monkeypatch) -> None:
    monkeypatch.setattr(ce.shutil, "which", lambda name: None)
    r = ce.run_code_snippet("javascript", "console.log(1)", isolation="process")
    assert "node runtime unavailable" in r.error
    assert ce.format_observation(r).startswith("[code_exec javascript]")


def test_isolation_misconfigured_returns_error() -> None:
    r = ce.run_code_snippet("python", "print(1)", isolation="ghost-backend")
    assert "isolation misconfigured" in r.error


def test_code_too_long_returns_error() -> None:
    r = ce.run_code_snippet("python", "x" * (ce.MAX_CODE_CHARS + 1), isolation="process")
    assert "code too long" in r.error


def test_launch_oserror_returns_error(monkeypatch) -> None:
    from realmock.platform.capabilities.ai.agent.tools.isolation import process as proc_mod

    def _boom(self, argv, *, cwd=None, env=None, timeout_s=None):
        raise OSError("no runtime")

    monkeypatch.setattr(proc_mod.ProcessIsolation, "spawn", _boom)
    # Force process backend instance so resolve_backend is bypassed.
    from realmock.platform.capabilities.ai.agent.tools.isolation.process import ProcessIsolation

    r = ce.run_code_snippet("python", "print(1)", isolation=ProcessIsolation())
    assert "failed to launch runtime" in r.error


def test_isolation_suffix_empty() -> None:
    empty = ce.CodeResult(language="python", exit_code=0, stdout="o", stderr="", duration_ms=1)
    assert ce._isolation_suffix(empty) == ""
    obs = ce.format_observation(empty)
    assert "isolation" not in obs


def test_format_timeout_and_truncated() -> None:
    timed = ce.CodeResult(
        language="python", exit_code=-1, stdout="part", stderr="",
        duration_ms=12, timed_out=True, isolation="process", notes=("cgroup=unavailable",),
    )
    obs = ce.format_observation(timed)
    assert "timeout" in obs
    assert "process" in obs
    trunc = ce.CodeResult(
        language="python", exit_code=0, stdout="o", stderr="e",
        duration_ms=1, truncated=True, isolation="process",
    )
    assert "(output truncated)" in ce.format_observation(trunc)
