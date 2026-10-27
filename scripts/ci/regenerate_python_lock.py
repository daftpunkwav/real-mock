"""Regenerate the CI lock from the manifest and refresh its manifest snapshot.

The lock is compiled with the exact command recorded in its header; this
script runs that command and then rewrites the trailing manifest-snapshot
block that ``check_python_lock_sync.py`` validates. The snapshot is what lets
the gate detect a changed extras request (``uvicorn[standard]`` to
``uvicorn``): it changes no resolved version, so the pins alone cannot show
it — only the recorded requirement strings can. Compiling and stamping are
one step on purpose: a snapshot written without the re-resolution behind it
could attest a tree the manifest no longer describes.

Usage::

    python scripts/ci/regenerate_python_lock.py
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
    with_snapshot,
)


def main() -> int:
    """Compile the lock with uv, then stamp the snapshot of the manifest."""
    # The exact command recorded in the lock header; keep both in sync.
    # Spelled out as a literal at the call site: the security scanners only
    # accept a literal, not a name resolved from elsewhere.
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
    expected = expected_snapshot(tomllib.loads(MANIFEST.read_text(encoding="utf-8")))
    LOCK.write_text(
        with_snapshot(LOCK.read_text(encoding="utf-8"), expected), encoding="utf-8"
    )
    print("lock compiled and manifest snapshot refreshed")
    print("verify with: python scripts/ci/check_python_lock_sync.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
