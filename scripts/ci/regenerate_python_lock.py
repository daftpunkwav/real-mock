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
current manifest; use it when the pins are known to be unaffected, e.g. after
a pure formatting edit to the manifest.
"""

from __future__ import annotations

import subprocess
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

# The lock header records this command verbatim; keep both in sync.
COMPILE_COMMAND = [
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
]


def main(argv: list[str]) -> int:
    """Compile the lock (unless --annotate-only) and refresh its snapshot."""
    annotate_only = "--annotate-only" in argv
    if not annotate_only:
        result = subprocess.run(COMPILE_COMMAND, cwd=ROOT, check=False)
        if result.returncode != 0:
            return result.returncode
    manifest = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    LOCK.write_text(
        with_snapshot(LOCK.read_text(encoding="utf-8"), expected_snapshot(manifest)),
        encoding="utf-8",
    )
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
