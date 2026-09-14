"""Shared isolation primitives for agent snippet execution (Step 2).

This module holds the capability contract every isolation backend must honor
plus the process-spawning helper they share, so timeout handling (kill the
whole process tree) stays identical across backends.

Contract rules: backends never raise for snippet behavior (exit codes and
timeouts are data), and any control they cannot enforce is reported as a
machine-readable entry in ``CompletedSnippet.notes`` instead of being
silently dropped.
"""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class CompletedSnippet:
    """Raw outcome of one sandboxed child run.

    ``stdout``/``stderr`` are raw bytes; output truncation stays with the
    caller (``codeexec``) so every backend is capped identically. ``notes``
    carries explicit degrade markers such as ``cgroup=unavailable``.
    """

    exit_code: int
    stdout: bytes
    stderr: bytes
    timed_out: bool
    notes: tuple[str, ...] = ()


@runtime_checkable
class IsolationBackend(Protocol):
    """Capability contract for snippet isolation backends."""

    name: str

    def spawn(
        self,
        argv: Sequence[str],
        *,
        cwd: str,
        env: Mapping[str, str],
        timeout_s: float,
    ) -> CompletedSnippet:
        """Run ``argv`` with ``cwd``/``env``; kill the tree on timeout.

        Must not raise for snippet behavior. ``OSError`` on launch failure
        is allowed and converted to an error result by the caller.
        """
        ...

    def describe(self) -> str:
        """One-line summary of the enforced controls (logs/observations)."""
        ...


def terminate_tree(proc: subprocess.Popen[bytes]) -> None:
    """Best-effort kill of a timed-out child (and its group on POSIX)."""
    try:
        if os.name == "posix":
            try:
                os.killpg(proc.pid, signal.SIGKILL)
                return
            except (ProcessLookupError, PermissionError, OSError):
                pass
        proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass


def run_child(
    argv: Sequence[str],
    *,
    cwd: str,
    env: Mapping[str, str],
    timeout_s: float,
    on_start: Callable[[int], None] | None = None,
) -> tuple[int, bytes, bytes, bool]:
    """Spawn ``argv`` and wait up to ``timeout_s`` seconds.

    Returns ``(exit_code, stdout, stderr, timed_out)``. ``on_start`` (if
    given) is invoked with the child pid right after spawn so callers can
    attach out-of-band controls such as a cgroup. Raises ``OSError`` when
    the runtime cannot be launched.
    """
    proc = subprocess.Popen(
        list(argv),
        cwd=cwd,
        env=dict(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=(os.name == "posix"),
    )
    if on_start is not None:
        on_start(proc.pid)
    try:
        out, err = proc.communicate(timeout=timeout_s)
        return proc.returncode, out, err, False
    except subprocess.TimeoutExpired:
        terminate_tree(proc)
        try:
            out, err = proc.communicate(timeout=5)
        except Exception:
            out, err = b"", b""
        return -1, out, err, True
