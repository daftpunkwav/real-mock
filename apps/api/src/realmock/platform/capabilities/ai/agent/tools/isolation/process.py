"""Process-level isolation backend: current behavior, Windows/dev default.

Enforces wall-clock timeout (whole process tree is killed on expiry) and
runs the snippet in a private temp working directory with a scrubbed
environment supplied by the caller. It does NOT switch users, block the
network, or cap cgroup resources; use the linux-job backend where the OS
supports it. Safe default wherever OS job controls are unavailable
(Windows, dev laptops, non-root processes).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .base import CompletedSnippet, run_child


class ProcessIsolation:
    """Child-process isolation without OS sandbox controls."""

    name = "process"

    def describe(self) -> str:
        """One-line summary of the enforced controls (logs/observations)."""
        return (
            "process isolation: timeout + private cwd + scrubbed env "
            "(no user switch, no network block, no cgroup caps)"
        )

    def spawn(
        self,
        argv: Sequence[str],
        *,
        cwd: str,
        env: Mapping[str, str],
        timeout_s: float,
    ) -> CompletedSnippet:
        """Run ``argv`` as a plain child process with timeout kill-tree."""
        exit_code, out, err, timed_out = run_child(
            argv, cwd=cwd, env=env, timeout_s=timeout_s
        )
        return CompletedSnippet(
            exit_code=exit_code, stdout=out, stderr=err, timed_out=timed_out
        )
