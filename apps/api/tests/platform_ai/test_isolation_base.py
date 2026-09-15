"""Isolation base tests for apps/api/src/realmock/platform/capabilities/ai/agent/tools/isolation/base.py.

Covers: terminate_tree POSIX/killpg-fallback paths and run_child success/launch-failure/
timeout branches including second-wait failure handling.

Conventions: no real containers (Popen/killpg mocked, one real short-lived python child); asyncio_mode=auto.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from realmock.platform.capabilities.ai.agent.tools.isolation import base as iso_base



def test_terminate_tree_current_platform() -> None:
    proc = MagicMock()
    proc.pid = 123
    iso_base.terminate_tree(proc)
    if os.name == "posix":
        proc.kill.assert_not_called()
    else:
        proc.kill.assert_called_once_with()


def test_terminate_tree_posix_killpg_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(iso_base.os, "name", "posix")
    # os.killpg / signal.SIGKILL do not exist on Windows; create them for the branch.
    monkeypatch.setattr(iso_base.os, "killpg", MagicMock(), raising=False)
    monkeypatch.setattr(iso_base.signal, "SIGKILL", 9, raising=False)
    proc = MagicMock()
    proc.pid = 4321
    iso_base.terminate_tree(proc)
    iso_base.os.killpg.assert_called_once_with(4321, 9)  # type: ignore[attr-defined]
    proc.kill.assert_not_called()
    iso_base.os.killpg.side_effect = OSError("gone")  # type: ignore[attr-defined]
    iso_base.terminate_tree(proc)
    proc.kill.assert_called_once_with()
    proc2 = MagicMock()
    proc2.kill.side_effect = PermissionError("denied")
    iso_base.terminate_tree(proc2)  # swallowed, never raises


def test_run_child_success_and_on_start(tmp_path: Any) -> None:
    seen: list[int] = []
    code, out, err, timed_out = iso_base.run_child(
        [sys.executable, "-c", "print('hi')"],
        cwd=str(tmp_path),
        env=dict(os.environ),
        timeout_s=30,
        on_start=seen.append,
    )
    assert code == 0 and out.strip() == b"hi" and err == b"" and timed_out is False
    assert len(seen) == 1 and seen[0] > 0


def test_run_child_launch_failure_raises(tmp_path: Any) -> None:
    with pytest.raises(OSError):
        iso_base.run_child(
            ["definitely-not-a-real-binary-xyz"],
            cwd=str(tmp_path),
            env=dict(os.environ),
            timeout_s=5,
        )


def test_run_child_timeout_paths() -> None:
    real_popen = subprocess.Popen

    def _fake_factory(second: Any) -> Any:
        proc = MagicMock()
        proc.pid = 777
        proc.returncode = -1
        proc.communicate = MagicMock(
            side_effect=[subprocess.TimeoutExpired("cmd", 1), second]
        )
        return proc

    with (
        patch.object(iso_base.subprocess, "Popen", return_value=_fake_factory((b"o", b"e"))),
        patch.object(iso_base, "terminate_tree") as term,
    ):
        assert real_popen is not None
        assert iso_base.run_child(["x"], cwd=".", env={}, timeout_s=1) == (-1, b"o", b"e", True)
        term.assert_called_once()
    with (
        patch.object(iso_base.subprocess, "Popen", return_value=_fake_factory(RuntimeError("x"))),
        patch.object(iso_base, "terminate_tree"),
    ):
        assert iso_base.run_child(["x"], cwd=".", env={}, timeout_s=1) == (-1, b"", b"", True)


@pytest.mark.asyncio
async def test_iso_base_terminate_and_run_child_timeout(monkeypatch) -> None:
    class _P:
        pid = 999
        killed = False

        def kill(self):
            self.killed = True

    monkeypatch.setattr(iso_base.os, "name", "posix")
    monkeypatch.setattr(
        iso_base.os, "killpg", lambda pid, sig: (_ for _ in ()).throw(OSError("x")), raising=False
    )
    import signal as _sig2

    monkeypatch.setattr(_sig2, "SIGKILL", 9, raising=False)
    iso_base.terminate_tree(_P())  # type: ignore[arg-type]

    class _FakeProc:
        pid = 7
        returncode = 0

        def communicate(self, timeout=None):
            if timeout == 5:
                raise RuntimeError("second wait fails")
            raise subprocess.TimeoutExpired(cmd="x", timeout=timeout)

        def kill(self):
            return None

    monkeypatch.setattr(iso_base.subprocess, "Popen", lambda *a, **k: _FakeProc())
    code, out, err, timed = iso_base.run_child(["x"], cwd=".", env={}, timeout_s=0.01)
    assert timed is True
    assert code == -1
    assert out == b""
