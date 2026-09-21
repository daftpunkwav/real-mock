"""Sandboxed code runner for agent self-verification (Step 2).

Lets an agent run a short Python / JavaScript snippet in a child process and
read back exit code, stdout, stderr and duration — "write code, run it, look
at the output" instead of guessing.

Isolation is capability-based (see the ``isolation`` subpackage) and picked
per call by ``run_code_snippet(..., isolation=...)``: ``"auto"`` (default)
uses the linux-job backend — dropped ``nobody``-style user, private network
namespace, cgroup v2 memory/cpu caps, best-effort read-only root — when
running as root on Linux, and falls back to process isolation elsewhere
(Windows, dev machines, non-root) with a one-time warning. Every control a
backend cannot enforce is reported back as an explicit note on the result,
never silently dropped.

What is always bounded regardless of backend: wall-clock timeout (the whole
process tree is killed on expiry), temp working directory (removed
afterwards), scrubbed environment (secrets/proxies dropped), input size and
captured output size.

This tool is for the first-party prep coach only; do not expose it to
untrusted callers without reviewing the active backend's notes first.
"""

from __future__ import annotations

import logging
import math
import os
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass

from .isolation import IsolationBackend, resolve_backend

logger = logging.getLogger(__name__)

# Model-facing language ids (aliases normalized in run_code_snippet).
LANGUAGE_PYTHON = "python"
LANGUAGE_JAVASCRIPT = "javascript"
_SUPPORTED_LANGUAGES = (LANGUAGE_PYTHON, LANGUAGE_JAVASCRIPT)
_LANGUAGE_ALIASES = {
    "py": LANGUAGE_PYTHON,
    "python3": LANGUAGE_PYTHON,
    "js": LANGUAGE_JAVASCRIPT,
    "node": LANGUAGE_JAVASCRIPT,
    "nodejs": LANGUAGE_JAVASCRIPT,
}

# Well under the prep tool_exec 18s budget so the outer wrapper never fires first.
DEFAULT_TIMEOUT_SEC = 10.0
MAX_TIMEOUT_SEC = 15.0
MAX_CODE_CHARS = 8_000
MAX_OUTPUT_CHARS = 6_000

# Minimal environment for the child: keeps PATH/TZ-style basics, drops
# secrets, tokens, API keys and proxies inherited from the server process.
_SAFE_ENV_KEYS = frozenset({
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP",
    "LANG", "LC_ALL", "LANGUAGE", "TZ", "HOME", "USER", "LOGNAME",
})

# Heuristic: ESM file suffix when the snippet uses import/export statements.
_ESM_RE = re.compile(r"^\s*(import\s.+?\sfrom\s+['\"]|export\s+(default\s|const\s|function\s|class\s|\{))", re.MULTILINE)


@dataclass(frozen=True)
class CodeResult:
    """Outcome of one snippet run (always returned, never raised)."""

    language: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    truncated: bool = False
    error: str = ""
    isolation: str = ""
    notes: tuple[str, ...] = ()


def _scrubbed_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS and v}


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"\n…[truncated {len(text) - limit} chars]", True


def run_code_snippet(
    language: str,
    code: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    isolation: str | IsolationBackend | None = None,
) -> CodeResult:
    """Run ``code`` in a child interpreter; never raises on snippet failure.

    Unknown languages, missing runtimes and oversized inputs become a
    :class:`CodeResult` with ``error`` set, so callers can render a model
    observation without branching on exceptions. ``isolation`` selects the
    sandbox backend (``"auto"`` default, ``"process"``, ``"linux-job"``, or a
    backend instance); a misconfigured selection is likewise an error
    result, never an exception.
    """
    normalized = str(language or "").strip().lower()
    lang = normalized if normalized in _SUPPORTED_LANGUAGES else _LANGUAGE_ALIASES.get(normalized, "")
    if lang not in _SUPPORTED_LANGUAGES:
        return CodeResult(
            language=str(language or ""),
            exit_code=-1,
            stdout="",
            stderr="",
            duration_ms=0,
            error=f"unsupported language {str(language or '')!r}; use one of {list(_SUPPORTED_LANGUAGES)}",
        )
    if not isinstance(code, str) or not code.strip():
        return CodeResult(
            language=lang, exit_code=-1, stdout="", stderr="",
            duration_ms=0, error="empty code; provide a complete runnable snippet",
        )
    if len(code) > MAX_CODE_CHARS:
        return CodeResult(
            language=lang, exit_code=-1, stdout="", stderr="",
            duration_ms=0,
            error=f"code too long ({len(code)} chars > {MAX_CODE_CHARS}); shrink the snippet",
        )
    try:
        timeout_s = min(max(float(timeout or DEFAULT_TIMEOUT_SEC), 1.0), MAX_TIMEOUT_SEC)
    except (TypeError, ValueError):
        timeout_s = DEFAULT_TIMEOUT_SEC
    if not math.isfinite(timeout_s):
        # NaN/inf would poison the child wait (ValueError deep in
        # threading) — fall back instead of raising out of a never-raise API.
        timeout_s = DEFAULT_TIMEOUT_SEC

    if lang == LANGUAGE_PYTHON:
        argv = [sys.executable, "-I", "snippet.py"]
        filename = "snippet.py"
    else:
        node = shutil.which("node")
        if not node:
            return CodeResult(
                language=lang, exit_code=-1, stdout="", stderr="",
                duration_ms=0, error="node runtime unavailable in this deployment",
            )
        filename = "snippet.mjs" if _ESM_RE.search(code) else "snippet.cjs"
        argv = [node, filename]

    start = time.monotonic()
    try:
        backend = resolve_backend(isolation)
    except (TypeError, ValueError, RuntimeError, OSError) as exc:
        return CodeResult(
            language=lang, exit_code=-1, stdout="", stderr="",
            duration_ms=int((time.monotonic() - start) * 1000),
            error=f"isolation misconfigured: {exc}",
        )
    try:
        with tempfile.TemporaryDirectory(prefix="codeexec-") as workdir:
            with open(os.path.join(workdir, filename), "w", encoding="utf-8") as fh:
                fh.write(code)
            completed = backend.spawn(
                argv,
                cwd=workdir,
                env=_scrubbed_env(),
                timeout_s=timeout_s,
            )
            out, err = completed.stdout, completed.stderr
            exit_code = completed.exit_code
            timed_out = completed.timed_out
            notes = completed.notes
    except OSError as exc:
        return CodeResult(
            language=lang, exit_code=-1, stdout="", stderr="",
            duration_ms=int((time.monotonic() - start) * 1000),
            error=f"failed to launch runtime: {exc}",
        )
    duration_ms = int((time.monotonic() - start) * 1000)
    stdout, cut_out = _truncate(out.decode("utf-8", errors="replace"))
    stderr, cut_err = _truncate(err.decode("utf-8", errors="replace"))
    return CodeResult(
        language=lang,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        timed_out=timed_out,
        truncated=cut_out or cut_err,
        isolation=backend.name,
        notes=notes,
    )


def _isolation_suffix(result: CodeResult) -> str:
    """Render the sandbox backend + degrade markers (empty when unknown)."""
    if not result.isolation:
        return ""
    suffix = f"\nisolation: {result.isolation}"
    if result.notes:
        suffix += f" ({'; '.join(result.notes)})"
    return suffix


def format_observation(result: CodeResult) -> str:
    """Render a :class:`CodeResult` as model-facing observation text."""
    if result.error:
        return (
            f"[code_exec {result.language or 'unknown'}] error: {result.error}"
        )
    if result.timed_out:
        return (
            f"[code_exec {result.language} timeout after {result.duration_ms}ms] "
            f"the snippet did not finish; simplify it or print progress. "
            f"Partial stdout:\n{result.stdout or '(empty)'}"
            f"{_isolation_suffix(result)}"
        )
    head = f"[code_exec {result.language} exit={result.exit_code} {result.duration_ms}ms]"
    parts = [head]
    parts.append(f"stdout:\n{result.stdout or '(empty)'}")
    if result.stderr:
        parts.append(f"stderr:\n{result.stderr}")
    if result.truncated:
        parts.append("(output truncated)")
    suffix = _isolation_suffix(result)
    if suffix:
        parts.append(suffix.lstrip("\n"))
    return "\n".join(parts)


__all__ = [
    "DEFAULT_TIMEOUT_SEC",
    "LANGUAGE_JAVASCRIPT",
    "LANGUAGE_PYTHON",
    "MAX_CODE_CHARS",
    "MAX_OUTPUT_CHARS",
    "CodeResult",
    "format_observation",
    "run_code_snippet",
]
