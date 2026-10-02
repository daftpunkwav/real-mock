"""Documentation bilingual pairing check.

The docs tree is maintained as bilingual pairs: X.md (English) and
X.zh.md (Chinese). A rename or a new page that lands in only one
language silently orphans readers of the other, so the pairing rule is
enforced here. Scanned: docs/ recursively plus the root README pair.
AGENTS/CONTRIBUTING-style root files are intentionally out of scope -
their language policy differs (see repo docs).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    problems: list[str] = []

    for md in sorted((ROOT / "docs").rglob("*.md")):
        rel = md.relative_to(ROOT)
        if md.name.endswith(".zh.md"):
            english = md.with_name(md.name[: -len(".zh.md")] + ".md")
            if not english.exists():
                problems.append(
                    f"{rel}: missing English counterpart {english.relative_to(ROOT)}"
                )
        else:
            chinese = md.with_name(md.name[: -len(".md")] + ".zh.md")
            if not chinese.exists():
                problems.append(
                    f"{rel}: missing Chinese counterpart {chinese.relative_to(ROOT)}"
                )

    root_readme = ROOT / "README.md"
    if root_readme.exists() and not (ROOT / "README.zh.md").exists():
        problems.append("README.md: missing Chinese counterpart README.zh.md")
    root_readme_zh = ROOT / "README.zh.md"
    if root_readme_zh.exists() and not (ROOT / "README.md").exists():
        problems.append("README.zh.md: missing English counterpart README.md")

    if problems:
        print("Unpaired documentation files:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("documentation pairs complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
