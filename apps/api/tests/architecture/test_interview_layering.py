"""AST guards for the interview domain layering (see ``agents/__init__.py``).

The ``agents`` execution chain is intentionally flat: subpackages are only
earned past ~400 lines in one file or 3+ new files in a cluster. Until then
these tests hold the seams instead of directories:

- external layers (realtime/routes/process) reach ``agents`` internals only
  through the facade or the three leaf contracts;
- ``agents`` never imports upward (realtime/routes);
- the facade export list stays in sync with its resolver map.
"""

from __future__ import annotations

import ast
from pathlib import Path

INTERVIEW_ROOT = Path("src/realmock/domains/interview")

#: Deep ``agents.<leaf>`` imports allowed outside ``agents`` (contracts/SSOT).
AGENTS_LEAF_ALLOWLIST = frozenset({"events", "workflows", "agent_text"})


def _api_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _from_imports(path: Path) -> list[tuple[str | None, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        (node.module, node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    ]


def _agents_submodule(module: str | None) -> str | None:
    """Return the ``<leaf>`` of ``realmock.domains.interview.agents.<leaf>...``."""
    if not module:
        return None
    parts = module.split(".")
    if parts[:4] == ["realmock", "domains", "interview", "agents"] and len(parts) > 4:
        return parts[4]
    return None


def test_interview_agents_facade_discipline() -> None:
    """realtime/routes/process import agents only via facade or leaf contracts."""
    api_root = _api_root()
    violations: list[str] = []
    for layer in ("realtime", "routes", "process"):
        base = api_root / INTERVIEW_ROOT / layer
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            for module, lineno in _from_imports(path):
                leaf = _agents_submodule(module)
                if leaf and leaf not in AGENTS_LEAF_ALLOWLIST:
                    violations.append(
                        f"{path.relative_to(api_root)}:{lineno}: deep import "
                        f"'{module}' — use the agents facade instead"
                    )
    assert not violations, (
        "external layers must not import agents internals directly:\n" + "\n".join(violations)
    )


def test_interview_agents_no_upward_imports() -> None:
    """agents never imports upward into realtime/routes."""
    api_root = _api_root()
    base = api_root / INTERVIEW_ROOT / "agents"
    violations: list[str] = []
    for path in sorted(base.rglob("*.py")):
        for module, lineno in _from_imports(path):
            if not module:
                continue
            parts = module.split(".")
            if (
                len(parts) >= 5
                and parts[:3] == ["realmock", "domains", "interview"]
                and parts[3] in ("realtime", "routes")
            ):
                violations.append(
                    f"{path.relative_to(api_root)}:{lineno}: upward import '{module}'"
                )
    assert not violations, (
        "agents must not depend on upper layers (dependency: realtime/routes → agents):\n"
        + "\n".join(violations)
    )


def test_interview_agents_facade_in_sync() -> None:
    """``__all__`` matches the lazy-resolver map (no dead/naked exports)."""
    api_root = _api_root()
    path = api_root / INTERVIEW_ROOT / "agents" / "__init__.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    all_names: set[str] = set()
    lazy_keys: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
            value = node.value
        else:
            continue
        if value is None:
            continue
        if "__all__" in targets and isinstance(value, (ast.List, ast.Tuple)):
            all_names = {
                e.value for e in value.elts if isinstance(e, ast.Constant)
            }
        if "_LAZY_EXPORTS" in targets and isinstance(value, ast.Dict):
            lazy_keys = {
                k.value for k in value.keys if isinstance(k, ast.Constant)
            }
    assert all_names, "agents/__init__.py must define __all__"
    assert all_names == lazy_keys, (
        f"facade __all__ out of sync with _LAZY_EXPORTS: "
        f"only-in-__all__={sorted(all_names - lazy_keys)}, "
        f"only-in-map={sorted(lazy_keys - all_names)}"
    )
