#!/usr/bin/env python3
"""Reject tracked paths that differ only by letter case.

Linux is case-sensitive; Windows and macOS (default) are not. A colliding pair
lives fine in a Linux checkout and silently breaks every clone on a
case-insensitive host - the filesystem can only hold one of them, so checkout
fails or whichever lands last overwrites the other. Git does not prevent the
pair from being committed (it only warns at checkout time, on the client doing
the checkout), so CI is the only place this can be enforced.

The check runs against the git index (``git ls-files``), not the working tree,
so it sees exactly what would be committed and fails on inventory errors rather
than silently passing because it scanned nothing.

Run from the repository root:

    python scripts/ci/check_case_collisions.py
"""

from __future__ import annotations

import subprocess  # CI script drives git  # nosec B404
import sys
from collections import defaultdict


def tracked_paths() -> list[str]:
    # -z: NUL-separated, so paths containing spaces or quotes survive intact.
    out = subprocess.run(  # fixed git argv, no shell  # nosec B603 B607
        ["git", "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    paths = [p for p in out.stdout.decode("utf-8", "surrogateescape").split("\0") if p]
    if not paths:
        raise SystemExit("no tracked files found - refusing to pass on an empty scan")
    return paths


def main() -> int:
    groups: dict[str, list[str]] = defaultdict(list)
    for path in tracked_paths():
        groups[path.casefold()].append(path)

    collisions = {k: v for k, v in groups.items() if len(v) > 1}
    if not collisions:
        print(f"ok - no case collisions among {len(groups)} tracked paths")
        return 0

    print(
        f"error - {len(collisions)} case-insensitive path collision(s) in the index:\n"
    )
    for key, paths in sorted(collisions.items()):
        print(f"  {key}")
        for path in sorted(paths):
            print(f"    {path}")
    print(
        "\nTwo tracked files differ only by case. They coexist on Linux and break "
        "checkouts on Windows and macOS.\nRename one, or squash the pair into a "
        "single path with `git mv` (force-add if git refuses)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
