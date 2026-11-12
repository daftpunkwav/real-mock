"""AST guard: literal error codes passed to ``raise_error`` / ``get_spec`` must be registered.

``platform/core/errors.py`` declares the CATALOG "authoritative; register new
codes here first", and ``get_spec`` silently falls back to ``B0001`` for an
unknown code. A typo in a ``raise_error("A1234")`` call therefore compiles,
passes review, and turns the intended 4xx/5xx contract into a generic 500 that
only surfaces in production. This guard holds the seam: every literal code
reachable from a source call site must exist in the CATALOG.

Dynamic arguments (``raise_error(exc.code)``) are out of the lexical net by
design; the self-check pins that only literal arguments are matched.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path("src/realmock")

#: Entry points that take an error code as their first positional argument.
_CODE_FUNCTIONS = frozenset({"raise_error", "get_spec"})


def _api_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _literal_codes(path: Path) -> list[tuple[str, int]]:
    """``(code, lineno)`` for every literal code argument in ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _CODE_FUNCTIONS
            and node.args
        ):
            continue
        argument = node.args[0]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            hits.append((argument.value, argument.lineno))
    return hits


def test_literal_error_codes_are_registered() -> None:
    from realmock.platform.core.errors import CATALOG

    violations: list[str] = []
    for path in sorted((_api_root() / SRC_ROOT).rglob("*.py")):
        for code, lineno in _literal_codes(path):
            if code not in CATALOG:
                violations.append(
                    f"{path.relative_to(_api_root())}:{lineno}: code '{code}' is "
                    "not registered in platform.core.errors.CATALOG"
                )
    assert not violations, (
        "error codes must be registered in the CATALOG (get_spec silently "
        "falls back to B0001/500 otherwise):\n" + "\n".join(violations)
    )


def test_error_code_guard_self_check(tmp_path: Path) -> None:
    """The guard matches literal keyword/positional codes and skips dynamic ones."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        "def f(exc):\n"
        '    raise_error("Z9999")\n'
        "    get_spec(exc.code)\n"
        '    raise_error("A0001", max=1)\n',
        encoding="utf-8",
    )
    assert _literal_codes(probe) == [("Z9999", 2), ("A0001", 4)]
