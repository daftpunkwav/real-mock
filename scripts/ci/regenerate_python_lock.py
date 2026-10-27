"""Regenerate the CI lock from the manifest and refresh its manifest snapshot.

The lock is compiled with the exact command recorded in its header; this
script runs that command and then rewrites the trailing manifest-snapshot
block that ``check_python_lock_sync.py`` validates. The snapshot is what lets
the gate detect a changed extras request (``uvicorn[standard]`` to
``uvicorn``): it changes no resolved version, so the pins alone cannot show
it — only the recorded requirement strings can.

Usage::

    python scripts/ci/regenerate_python_lock.py
    python scripts/ci/regenerate_python_lock.py --annotate-only

``--annotate-only`` skips the uv compile and refreshes the snapshot from the
current manifest. Only for manifest edits the lock cannot see: comments,
whitespace, or reordering a requirements array. After changing a
Usage::

    python scripts/ci/regenerate_python_lock.py
    python scripts/ci/regenerate_python_lock.py --annotate-only

``--annotate-only`` skips the uv compile and refreshes the snapshot. It
refuses to run when the lock already carries a snapshot that differs from
the current manifest: that difference means the lock was compiled from a
different manifest, and the pins may no longer reflect it — the gate
compares pinned versions and the snapshot records strings, so neither can
catch a stale pin behind a freshly stamped snapshot. A missing block (uv
overwrites the lock on a bare compile) or an already matching one are the
only annotations it performs; a changed manifest always takes the full
compile.
"""

from __future__ import annotations

import subprocess  # the script drives uv  # nosec B404
import sys
from pathlib import Path

import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_python_lock_sync import (
    LOCK,
    MANIFEST,
    ROOT,
    expected_snapshot,
    snapshot_entries,
    with_snapshot,
)


def _annotate_only_blocked(expected: list[str], lock_text: str) -> str | None:
    """Why annotate-only must not stamp the snapshot, or None when it may.

    A lock whose recorded snapshot differs from the current manifest was
    compiled from a different manifest, so the pins may no longer reflect
    it; stamping the new strings would attest a tree the manifest no longer
    describes. Only the full compile re-resolves the pins.
    """
    recorded = snapshot_entries(lock_text)
    if recorded is not None and recorded != expected:
        return (
            "the lock records a different manifest than the current one; "
            "run the full compile instead of --annotate-only"
        )
    return None


def main(argv: list[str]) -> int:
    """Compile the lock (unless --annotate-only) and refresh its snapshot."""
    annotate_only = "--annotate-only" in argv
    if not annotate_only:
        # The exact command recorded in the lock header; keep both in sync.
        # Spelled out as a literal at the call site: the security scanners
        # only accept a literal, not a name resolved from elsewhere.
        result = subprocess.run(  # fixed uv argv, no shell  # nosec B603 B607
            [
                "uv",
                "pip",
                "compile",
                "apps/api/pyproject.toml",
                "--extra",
                "dev",
                "--generate-hashes",
                "--python-platform",
                "linux",
                "--python-version",
                "3.14",
                "--output-file",
                "apps/api/requirements-ci.lock",
            ],
            cwd=ROOT,
            check=False,
        )
        if result.returncode != 0:
            return result.returncode
    manifest = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = expected_snapshot(manifest)
    lock_text = LOCK.read_text(encoding="utf-8")
    if annotate_only:
        blocked = _annotate_only_blocked(expected, lock_text)
        if blocked is not None:
            print(blocked)
            return 1
    LOCK.write_text(with_snapshot(lock_text, expected), encoding="utf-8")
    if annotate_only:
        print(
            "manifest snapshot refreshed; the pins were not re-resolved (--annotate-only)"
        )
    else:
        print("lock compiled and manifest snapshot refreshed")
    print("verify with: python scripts/ci/check_python_lock_sync.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
