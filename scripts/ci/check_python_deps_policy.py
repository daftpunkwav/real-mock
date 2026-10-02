"""Dependency policy check (pip side): fail on any banned distribution in the
installed environment - direct or transitive. Runs inside the backend job
after `pip install -e 'apps/api[dev]'`, so the scanned set is exactly what
would ship. Names are PEP 503 normalized (lowercase, dashes collapsed)."""

from __future__ import annotations

import json
import re
from importlib import metadata
from pathlib import Path

POLICY = Path(__file__).resolve().parent / "dependency-policy.json"


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    banned = {canonical(name): reason for name, reason in policy.get("pip", {}).items()}

    installed: dict[str, str] = {}
    for dist in metadata.distributions():
        name = canonical(dist.metadata["Name"] or "")
        installed[name] = dist.version

    violations = sorted(name for name in installed if name in banned)
    if violations:
        print("banned pip dependencies present:")
        for name in violations:
            print(f"  - {name} {installed[name]}: {banned[name]}")
        return 1
    print(f"pip dependency policy ok ({len(installed)} distributions scanned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
