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
    # newline="\n" is explicit on purpose: the default translates to os.linesep,
    # so regenerating on Windows would rewrite every line as CRLF and leave a
    # working-tree diff that contradicts .editorconfig (and the committed blob).
    OUT.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"written {OUT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
