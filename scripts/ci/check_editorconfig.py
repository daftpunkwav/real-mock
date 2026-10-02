#!/usr/bin/env python3
"""Verify committed blobs against the repository's .editorconfig contract.

.editorconfig only configures editors; nothing in CI reads it, so a file can be
committed with CRLF endings, a missing final newline, trailing whitespace or tab
indentation, and every contributor then sees a different diff depending on which
editor they use.

The content is read from the git index rather than the working tree on purpose:
with core.autocrlf=true the checkout holds CRLF even though the stored blob is
LF, so a working-tree scan would report ~1300 false violations. .editorconfig
says the same thing: saving as LF still commits to the same normalized blob.

Enforced (exactly what .editorconfig declares):
  * end_of_line lf                 - no CRLF in the stored blob
  * insert_final_newline           - ends with exactly one newline
  * indent_style space             - no leading tab indentation
  * trim_trailing_whitespace       - every file type except markdown, where two
                                      trailing spaces are a hard line break

Run from the repository root:

    python scripts/ci/check_editorconfig.py
"""

from __future__ import annotations

import subprocess
import sys
from collections import defaultdict

SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".avif", ".pdf", ".zip",
    ".gz", ".tar", ".whl", ".so", ".dll", ".dylib", ".exe", ".bin", ".wasm",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp4", ".mp3", ".wav", ".db",
    ".sqlite", ".sqlite3", ".pack", ".idx", ".onnx", ".safetensors", ".pt",
    ".pyc", ".pyo",
}
SKIP_DIR_PARTS = {"node_modules", ".next", ".venv", "venv", "target", "dist",
                  "build", "coverage", ".git", "__pycache__", ".pytest_cache",
                  ".ruff_cache", ".mypy_cache", ".idea"}


def index_blobs() -> list[tuple[str, str]]:
    """(sha, path) for every staged/tracked file, from the index itself."""
    out = subprocess.run(["git", "ls-files", "-s", "-z"], check=True, capture_output=True)
    entries = []
    for rec in out.stdout.decode("utf-8", "surrogateescape").split("\0"):
        if not rec:
            continue
        meta, _, path = rec.partition("\t")
        parts = meta.split()
        if len(parts) < 2:
            continue
        entries.append((parts[1], path))
    return entries


def read_blobs(shas: list[str]) -> dict[str, bytes]:
    """Batch-read blob contents; one git process instead of one per file."""
    proc = subprocess.run(["git", "cat-file", "--batch"], input="\n".join(shas).encode(),
                          check=True, capture_output=True)
    out = proc.stdout
    blobs: dict[str, bytes] = {}
    pos = 0
    while pos < len(out):
        nl = out.find(b"\n", pos)
        if nl < 0:
            break
        header = out[pos:nl].split()
        pos = nl + 1
        if len(header) < 3:
            continue
        sha, size = header[0].decode(), int(header[2])
        blobs[sha] = out[pos:pos + size]
        pos += size + 1  # trailing newline after the payload
    return blobs


def main() -> int:
    entries = index_blobs()
    if not entries:
        raise SystemExit("no tracked files found - refusing to pass on an empty scan")

    wanted = [(sha, p) for sha, p in entries
              if not any(part in SKIP_DIR_PARTS for part in p.split("/"))
              and "." + p.rsplit(".", 1)[-1].lower() not in SKIP_SUFFIXES
              if "." in p.rsplit("/", 1)[-1]]
    blobs = read_blobs([sha for sha, _ in wanted])

    problems: dict[str, list[str]] = defaultdict(list)
    checked = 0

    for sha, rel in wanted:
        data = blobs.get(sha)
        if data is None or b"\0" in data[:8000]:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            problems["not valid utf-8"].append(rel)
            continue
        checked += 1

        if "\r\n" in text:
            problems["CRLF line endings (.editorconfig says lf)"].append(rel)
        if text and not text.endswith("\n"):
            problems["missing final newline"].append(rel)
        elif text.endswith("\n\n"):
            problems["multiple trailing newlines"].append(rel)
        if not rel.endswith(".md"):
            for i, line in enumerate(text.splitlines(), 1):
                if line != line.rstrip():
                    problems["trailing whitespace"].append(f"{rel}:{i}")
                if line.startswith("\t"):
                    problems["tab indentation (indent_style = space)"].append(f"{rel}:{i}")

    if not problems:
        print(f"ok - {checked} committed text blobs satisfy .editorconfig")
        return 0

    total = sum(len(v) for v in problems.values())
    print(f"error - {total} violation(s) in {checked} committed text blobs:\n")
    for rule, items in sorted(problems.items()):
        print(f"  {rule}  ({len(items)})")
        for item in items[:10]:
            print(f"    {item}")
        if len(items) > 10:
            print(f"    ... and {len(items) - 10} more")
        print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
