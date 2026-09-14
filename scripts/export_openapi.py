"""Export the aggregated FastAPI OpenAPI JSON (for frontend openapi-typescript generation).

Writes openapi.json at repo root.
Prerequisite: realmock-api installed (``pip install -e ./apps/api``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "openapi.json"


def main() -> None:
    from realmock.asgi import app

    schema = app.openapi()
    OUT.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written {OUT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
