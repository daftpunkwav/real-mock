"""The platform layer must not import business domains or composition-root bootstrap code (enforced by an AST guard)."""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_PREFIXES = ("realmock.domains", "realmock.bootstrap")
SCAN_ROOT = Path("src/realmock/platform")


def _forbidden_service_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            prefix = ".".join(node.module.split(".")[:2])
            if prefix in FORBIDDEN_PREFIXES:
                hits.append(f"from {node.module} import ... (line {node.lineno})")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                prefix = ".".join(alias.name.split(".")[:2])
                if prefix in FORBIDDEN_PREFIXES:
                    hits.append(f"import {alias.name} (line {node.lineno})")
    return hits


def test_platform_package_no_domain_imports() -> None:
    api_root = Path(__file__).resolve().parents[2]
    base = api_root / SCAN_ROOT
    violations: list[str] = []
    for path in base.rglob("*.py"):
        if "tests" in path.parts:
            continue
        for hit in _forbidden_service_imports(path):
            violations.append(f"{path.relative_to(api_root)}: {hit}")
    assert not violations, (
        "platform must not import business domains; see realmock.bootstrap.sessions_orm for session ORM registration:\n"
        + "\n".join(violations)
    )
