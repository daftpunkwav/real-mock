"""Snippet isolation backends and backend selection (Step 2).

``ProcessIsolation`` is the safe default wherever OS job controls are
unavailable (Windows, dev machines, non-root). ``LinuxJobIsolation`` adds a
dropped user, a private network namespace and cgroup v2 caps on Linux.
``resolve_backend`` picks between them: ``auto`` (default) sniffs the
platform, while an explicit name or instance forces one backend — a forced
backend that cannot run raises a clear error instead of falling back.
"""

from __future__ import annotations

import logging
import os
import sys

from .base import CompletedSnippet, IsolationBackend
from .linux_job import LinuxJobIsolation
from .process import ProcessIsolation

logger = logging.getLogger(__name__)

# Neutral override for backend selection: auto | process | linux-job.
SELECTION_ENV_VAR = "CODEEXEC_ISOLATION"

_BACKEND_ALIASES = {
    "auto": "auto",
    "process": "process",
    "linux-job": "linux-job",
    "linux_job": "linux-job",
    "linuxjob": "linux-job",
}

_warned_fallback = False


def _warn_once(message: str, *args: object) -> None:
    """Log a fallback warning only once per process (snippets are frequent)."""
    global _warned_fallback
    if _warned_fallback:
        return
    _warned_fallback = True
    logger.warning(message, *args)


def _running_as_root() -> bool:
    return (
        os.name == "posix"
        and sys.platform.startswith("linux")
        and hasattr(os, "geteuid")
        and os.geteuid() == 0
    )


def resolve_backend(selection: str | IsolationBackend | None = None) -> IsolationBackend:
    """Resolve which isolation backend runs the next snippet.

    ``None``/``"auto"`` reads the ``CODEEXEC_ISOLATION`` env var (default
    ``"auto"``): Linux root gets ``LinuxJobIsolation``, everything else gets
    ``ProcessIsolation`` with a one-time warning. An explicit backend name or
    instance is honored as-is; unknown names raise ``ValueError`` and a
    ``linux-job`` request off Linux raises ``RuntimeError``.
    """
    if selection is None:
        raw = os.environ.get(SELECTION_ENV_VAR, "auto")
    elif isinstance(selection, str):
        raw = selection.strip() or os.environ.get(SELECTION_ENV_VAR, "auto")
        if raw.strip().lower() == "auto":
            raw = "auto"
    elif hasattr(selection, "spawn") and hasattr(selection, "name"):
        return selection
    else:
        raise TypeError(
            "isolation must be a backend name, a backend instance, or None; "
            f"got {type(selection).__name__}"
        )
    key = raw.strip().lower()
    if key not in _BACKEND_ALIASES:
        raise ValueError(
            f"unknown isolation backend {raw!r}; "
            "use 'auto', 'process', or 'linux-job' "
            f"(or set {SELECTION_ENV_VAR} to one of these)"
        )
    kind = _BACKEND_ALIASES[key]
    if kind == "process":
        return ProcessIsolation()
    if kind == "linux-job":
        return LinuxJobIsolation()
    if _running_as_root():
        try:
            return LinuxJobIsolation()
        except (RuntimeError, ValueError, OSError) as exc:
            _warn_once(
                "codeexec: linux-job isolation unavailable (%s); "
                "falling back to process isolation",
                exc,
            )
            return ProcessIsolation()
    _warn_once(
        "codeexec: running with process isolation only "
        "(no user switch / network block / cgroup caps on this platform); "
        "deploy on Linux as root for linux-job isolation"
    )
    return ProcessIsolation()


__all__ = [
    "SELECTION_ENV_VAR",
    "CompletedSnippet",
    "IsolationBackend",
    "LinuxJobIsolation",
    "ProcessIsolation",
    "resolve_backend",
]
