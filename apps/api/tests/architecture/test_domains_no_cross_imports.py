"""AST guard: domain packages must not import sibling domain packages."""

from __future__ import annotations

import ast
from pathlib import Path

DOMAINS_ROOT = Path("src/realmock/domains")


def _discover_domains(domains_root: Path) -> set[str]:
    """Return domain package names from directories under domains/."""
    names: set[str] = set()
    if not domains_root.is_dir():
        return names
    for child in domains_root.iterdir():
        if child.is_dir() and not child.name.startswith("_") and child.name != "tests":
            if (child / "__init__.py").exists() or any(child.rglob("*.py")):
                names.add(child.name)
    return names


def _imported_domain(module: str | None) -> str | None:
    """If ``module`` is ``realmock.domains.<name>...``, return ``<name>``."""
    if not module:
        return None
    parts = module.split(".")
    if len(parts) >= 3 and parts[0] == "realmock" and parts[1] == "domains":
        return parts[2]
    return None


def _cross_domain_imports(path: Path, own_domain: str, known: set[str]) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            other = _imported_domain(node.module)
            if other and other in known and other != own_domain:
                hits.append(f"from {node.module} import ... (line {node.lineno})")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                other = _imported_domain(alias.name)
                if other and other in known and other != own_domain:
                    hits.append(f"import {alias.name} (line {node.lineno})")
    return hits


def test_domains_no_cross_imports() -> None:
    api_root = Path(__file__).resolve().parents[2]
    domains_root = api_root / DOMAINS_ROOT
    known = _discover_domains(domains_root)
    assert known, f"expected domain packages under {domains_root}"

    violations: list[str] = []
    for domain in sorted(known):
        base = domains_root / domain
        for path in base.rglob("*.py"):
            if "tests" in path.parts:
                continue
            for hit in _cross_domain_imports(path, domain, known):
                violations.append(f"{path.relative_to(api_root)}: {hit}")

    assert not violations, (
        "domains must not import sibling domains; wire via platform contracts / composition root:\n"
        + "\n".join(violations)
    )
