#!/usr/bin/env python3
"""Fail if CJK prose appears outside locale catalogs (intended: web i18n/messages; currently reports violations, see output).

Allowed (intended):
  - apps/web/src/i18n/messages/**
  - full-width punctuation glyphs alone in utility regexes (cnText / prompts)

Usage (repo root):
  python scripts/check_no_cjk.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CJK = re.compile(r"[\u4e00-\u9fff]")
# Full-width punctuation / symbols that may appear in English comments as examples
# NOTE: FW_ONLY/line_ok currently unused.
FW_ONLY = re.compile(
    r"^[\s\W\dA-Za-z_,.;:'\"`\-\[\](){}/\\|+=<>*!@#$%^&~"
    r"，。；：！？、（）「」《》【】…—–]*$"
)

SKIP_DIR_NAMES = {
    "node_modules",
    ".git",
    "__pycache__",
    "dist",
    ".next",
    "docs-local",
    "generated",
    "messages",  # under i18n/messages — handled via path check
}

SCAN_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx"}


def is_allowed(path: Path) -> bool:
    parts = path.parts
    if "i18n" in parts and "messages" in parts:
        return True
    return False


def line_ok(line: str) -> bool:
    if not CJK.search(line):
        return True
    # Allow lines that only contain CJK as full-width punct examples, no Han letters... 
    # Han is in \u4e00-\u9fff so FW_ONLY cannot contain Han. Any Han fails.
    return False


def main() -> int:
    offenders: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.suffix not in SCAN_SUFFIXES:
            continue
        if is_allowed(path):
            continue
        # Only scan apps/web/ + apps/api/src/ + apps/api/tests/ (scripts/protocol excluded by design).
        rel = path.relative_to(ROOT).as_posix()
        if not (rel.startswith("apps/web/src/") or rel.startswith("apps/api/src/") or rel.startswith("apps/api/tests/") or rel.startswith("apps/web/")):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        bad_lines: list[int] = []
        for i, line in enumerate(text.splitlines(), 1):
            if CJK.search(line):
                # Exception: cnText / prompts punctuation utility lines with mixed ASCII+FW punct
                if "cnText" in rel or rel.endswith("prompts.py"):
                    # strip Han letters check: if any Han syllable present, still fail
                    if re.search(r"[\u4e00-\u9fff]", line):
                        # allow if the only CJK are known fullwidth punct
                        if re.fullmatch(
                            r"[^\u4e00-\u9fff]*[，。；：！？、（）「」《》【】…—–]+[^\u4e00-\u9fff]*",
                            line,
                        ) or "full-width" in line.lower() or "fullwidth" in line.lower():
                            # still may contain Han — fail if Han letters
                            if re.search(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", line):
                                # Count Han vs punct — simple: if any CJK letter that's not punct
                                tmp = line
                                for ch in "，。；：！？、（）「」《》【】…—–":
                                    tmp = tmp.replace(ch, "")
                                if CJK.search(tmp):
                                    bad_lines.append(i)
                            continue
                bad_lines.append(i)
        if bad_lines:
            offenders.append(f"{rel}: lines {bad_lines[:8]}{'…' if len(bad_lines) > 8 else ''}")

    if offenders:
        print(f"CJK found outside locale catalogs ({len(offenders)} files):")
        for row in offenders[:80]:
            print(" ", row)
        if len(offenders) > 80:
            print(f"  … and {len(offenders) - 80} more")
        return 1
    print("OK: no CJK outside allowed locale catalogs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
