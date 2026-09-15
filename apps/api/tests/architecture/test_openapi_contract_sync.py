"""Contract freshness guard: the committed openapi.json must match the live app schema.

The REST contract pipeline is manual (``app.openapi()`` -> ``scripts/export_openapi.py``
-> ``openapi.json`` -> openapi-typescript). This test fails when the committed JSON
drifts from the current routes, so regeneration cannot be forgotten.
"""

from __future__ import annotations

import json
from pathlib import Path

from realmock.asgi import app

REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACT = REPO_ROOT / "openapi.json"


def test_committed_openapi_matches_app_schema() -> None:
    assert CONTRACT.is_file(), f"missing {CONTRACT}; run scripts/export_openapi.py"
    committed = json.loads(CONTRACT.read_text(encoding="utf-8"))
    live = app.openapi()
    drifted = sorted(
        key for key in set(committed) | set(live) if committed.get(key) != live.get(key)
    )
    assert committed == live, (
        f"openapi.json is stale relative to the current routes (drifted sections: {drifted}); "
        "regenerate with: python scripts/export_openapi.py"
    )
