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
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import IO, Protocol, runtime_checkable


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


# Hard safety net for captured child output per stream. Callers apply their own
# much smaller model-facing cap (codeexec: MAX_OUTPUT_CHARS); this only bounds
# parent-process memory so a chatty snippet cannot exhaust it before the timeout.
_CAPTURE_LIMIT_BYTES = 2 * 1024 * 1024
_READ_CHUNK_BYTES = 65536


def _pump_stream(
    stream: IO[bytes], buf: bytearray, limit: int, lock: threading.Lock
) -> None:
    """Drain ``stream`` into ``buf`` up to ``limit``; excess is discarded.

    Draining (instead of stopping at the limit) keeps the child unblocked so a
    chatty snippet still exits on its own instead of stalling until the
    timeout kill.
    """
    try:
        while True:
            chunk = stream.read(_READ_CHUNK_BYTES)
            if not chunk:
                break
            with lock:
                remaining = limit - len(buf)
                if remaining > 0:
                    buf += chunk[:remaining]
    except (OSError, ValueError):
        # Pipe closed mid-read (e.g. grandchild inherited and dropped it).
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

    Captured output is drained through a per-stream cap
    (``_CAPTURE_LIMIT_BYTES``): memory stays bounded no matter how much the
    child prints, while draining (not hard-closing at the cap) keeps the
    child unblocked so exit behavior is unchanged.
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
    out_buf, err_buf = bytearray(), bytearray()
    lock = threading.Lock()
    pumps = [
        threading.Thread(
            target=_pump_stream,
            args=(proc.stdout, out_buf, _CAPTURE_LIMIT_BYTES, lock),
            daemon=True,
        ),
        threading.Thread(
            target=_pump_stream,
            args=(proc.stderr, err_buf, _CAPTURE_LIMIT_BYTES, lock),
            daemon=True,
        ),
    ]
    for t in pumps:
        t.start()
    try:
        proc.wait(timeout=timeout_s)
        timed_out = False
    except subprocess.TimeoutExpired:
        terminate_tree(proc)
        timed_out = True
    # Reap the child after a timeout kill; grandchildren that inherited the
    # pipes may keep a pump blocked, so the join is bounded.
    proc.wait()
    for t in pumps:
        t.join(timeout=5)
    if timed_out:
        # Contract: a timeout is reported as exit_code -1 regardless of the
        # signal the platform reaps the killed tree with.
        return -1, bytes(out_buf), bytes(err_buf), True
    return proc.returncode, bytes(out_buf), bytes(err_buf), False
