"""AST guards for the interview domain layering (see ``agents/__init__.py``).

``agents`` hosts one subpackage per LLM role (interviewer / topology / hint /
planning / research / memory) with the shared machinery flat at the package
root. These tests hold the seams:

- external layers (realtime/routes/process) reach ``agents`` internals only
  through the facade or the two leaf contracts;
- ``agents`` never imports upward (realtime/routes);
- ``process`` never imports upward (agents) — every LLM role lives under
  ``agents``;
- shared stored-process documents (plan/round-plan/memory/round chain) live
  in the neutral ``protocols`` package both ``agents`` and ``process`` read;
- ``agents`` may call exactly one ``process`` module (the finish-path
  subscriber below) — any other agents→process edge fails this test;
- the WS entry (``routes/ws``) is the single wire into ``realtime``;
- the facade export list stays in sync with its resolver map.
"""

from __future__ import annotations

import ast
from pathlib import Path

INTERVIEW_ROOT = Path("src/realmock/domains/interview")

#: Deep ``agents.<leaf>`` imports allowed outside ``agents`` (contracts/SSOT).
#: The phase SSOT lives at the domain root (``interview.workflows``).
AGENTS_LEAF_ALLOWLIST = frozenset({"events", "agent_text"})

#: ``process.*`` modules ``agents`` may import. Everything shared (stored plan
#: protocols, process-memory documents, round chain) lives in the neutral
#: ``interview.protocols`` package, so exactly one downward edge remains:
#:
#: finish_lifecycle → record_round_finished: completion subscriber (never
#: raises, never calls back into agents — verified acyclic). Splitting it
#: across the 4 finish call sites would scatter the guarantee instead.
#: Any NEW agents→process edge fails this test and forces the discussion.
#: The reverse direction is banned outright by
#: :func:`test_interview_process_never_imports_agents`.
AGENTS_PROCESS_ALLOWLIST = frozenset({
    "realmock.domains.interview.process.process_service",
})


def _api_root() -> Path:
    return Path(__file__).resolve().parents[2]


_AGENTS_PACKAGE = "realmock.domains.interview.agents"


def _import_edges(path: Path) -> list[tuple[str, int]]:
    """Absolute module reference for every import in ``path``.

    This sees all three import forms — ``from X import y`` (relative levels
    resolved against the file's package), plain ``import X.Y``, and the
    package-level facade form ``from <package> import name`` — so dependency
    bans cannot be walked around by switching import style.
    """
    rel = path.relative_to(_api_root() / "src" / "realmock")
    package = ("realmock", *rel.parts[:-1])
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    edges: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                cut = len(package) - (node.level - 1)
                if cut < 1:
                    continue  # level escapes the realmock tree; not our seam
                base = package[:cut]
            else:
                if not node.module:
                    continue
                base = ()
            if node.module:
                base = (*base, *node.module.split("."))
            if base:
                edges.append((".".join(base), node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                edges.append((alias.name, node.lineno))
    return edges


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
            for module, lineno in _import_edges(path):
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
        for module, lineno in _import_edges(path):
            parts = module.split(".")
            if (
                len(parts) >= 4
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


def test_interview_agents_process_seam_frozen() -> None:
    """agents→process stays within the shared-kernel allowlist (no new edges)."""
    api_root = _api_root()
    base = api_root / INTERVIEW_ROOT / "agents"
    violations: list[str] = []
    for path in sorted(base.rglob("*.py")):
        for module, lineno in _import_edges(path):
            parts = module.split(".")
            if (
                parts[:4] == ["realmock", "domains", "interview", "process"]
                and module not in AGENTS_PROCESS_ALLOWLIST
            ):
                violations.append(
                    f"{path.relative_to(api_root)}:{lineno}: new agents→process edge "
                    f"'{module}' — extend AGENTS_PROCESS_ALLOWLIST deliberately or move the module"
                )
    assert not violations, (
        "agents→process seam is frozen to the shared-kernel allowlist:\n"
        + "\n".join(violations)
    )


def test_interview_process_never_imports_agents() -> None:
    """process must never import upward into agents (one-way layering).

    Every LLM role lives under ``agents`` (runners, topology, planning,
    research), so process has nothing left to reach for: the dependency rule
    is routes → realtime → agents → process, and this test proves the
    agents→process direction is the only seam. All import forms count —
    deep from-imports, package-level facade imports, plain ``import``
    statements, and relative imports.
    """
    api_root = _api_root()
    base = api_root / INTERVIEW_ROOT / "process"
    violations: list[str] = []
    for path in sorted(base.rglob("*.py")):
        for module, lineno in _import_edges(path):
            if module == _AGENTS_PACKAGE or module.startswith(_AGENTS_PACKAGE + "."):
                violations.append(
                    f"{path.relative_to(api_root)}:{lineno}: upward import '{module}'"
                )
    assert not violations, (
        "process must not depend on agents (dependency: agents → process):\n"
        + "\n".join(violations)
    )


def test_interview_routes_realtime_single_wire() -> None:
    """Only the WS entry (routes/ws) may wire into realtime (the handler)."""
    api_root = _api_root()
    violations: list[str] = []
    for layer in ("routes",):
        base = api_root / INTERVIEW_ROOT / layer
        for path in sorted(base.rglob("*.py")):
            in_ws_entry = "routes/ws" in path.as_posix().replace("\\", "/")
            for module, lineno in _import_edges(path):
                parts = module.split(".")
                if parts[:4] != ["realmock", "domains", "interview", "realtime"]:
                    continue
                allowed = (
                    in_ws_entry
                    and module == "realmock.domains.interview.realtime.ws_handler"
                )
                if not allowed:
                    violations.append(
                        f"{path.relative_to(api_root)}:{lineno}: routes→realtime edge "
                        f"'{module}' outside the WS entry wire"
                    )
    assert not violations, (
        "routes must not reach into realtime except via routes/ws → ws_handler:\n"
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
