"""With dual databases, the interview/agent domains must not directly import shared-table ORM models."""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN = frozenset({"Resume", "UserProfile"})
SCAN_ROOTS = (
    Path("src/realmock/domains/interview"),
    Path("src/realmock/domains/prep"),
)


def _imports_resume_or_profile(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "realmock.platform.models":
                hits.extend(
                    f"from realmock.platform.models import {alias.name}"
                    for alias in node.names
                    if alias.name in FORBIDDEN
                )
            elif node.module == "realmock.platform" and any(
                alias.name == "models" for alias in node.names
            ):
                hits.append("from realmock.platform import models")
        elif isinstance(node, ast.Import):
            hits.extend(
                f"import {alias.name}"
                for alias in node.names
                if alias.name == "realmock.platform.models"
                or alias.name.startswith("realmock.platform.models.")
            )
    return hits


def test_interview_agent_no_direct_shared_resume_imports() -> None:
    services = Path(__file__).resolve().parents[2]
    violations: list[str] = []
    for root in SCAN_ROOTS:
        base = services / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if "tests" in path.parts or path.name == "__init__.py":
                continue
            for hit in _imports_resume_or_profile(path):
                violations.append(f"{path.relative_to(services)}: {hit}")
    assert not violations, "The profile/resume should be read via candidate_read:\n" + "\n".join(violations)
