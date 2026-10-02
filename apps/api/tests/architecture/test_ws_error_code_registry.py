"""AST guard: WS-emitted error codes must exist in the platform error CATALOG.

The interview WS frames carry ``code=`` literals, and the front-end error
maps (``apps/web/src/i18n/messages/*/errors.ts``) declare themselves a
mirror of the backend CATALOG — so a code emitted on the wire but absent
from the CATALOG is an undeclared cross-layer contract. This test holds
the seam: every literal ``code="X"`` in the interview domain's WS-emitting
layers (``realtime`` and ``agents``, whose ``StreamEvent`` errors surface
as error frames) must be registered.

Best-effort lexical net: it sees literal keyword arguments only, not
variables or dynamic construction.
"""

from __future__ import annotations

import ast
from pathlib import Path

INTERVIEW_ROOT = Path("src/realmock/domains/interview")

#: Pre-existing wire codes not yet registered in the CATALOG. All interview
#: wire codes are registered now; keep the mechanism so a future unregistered
#: literal still fails here instead of shipping an undeclared contract.
LEGACY_UNREGISTERED: frozenset[str] = frozenset()


def _api_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _emitted_codes(path: Path) -> list[tuple[str, int]]:
    """``(code, lineno)`` for every literal ``code="..."`` keyword argument."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.keyword)
            and node.arg == "code"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            hits.append((node.value.value, node.value.lineno))
    return hits


def test_ws_error_codes_are_registered() -> None:
    from realmock.platform.core.errors import CATALOG

    violations: list[str] = []
    for layer in ("realtime", "agents"):
        base = _api_root() / INTERVIEW_ROOT / layer
        for path in sorted(base.rglob("*.py")):
            for code, lineno in _emitted_codes(path):
                if code in CATALOG or code in LEGACY_UNREGISTERED:
                    continue
                violations.append(
                    f"{path.relative_to(_api_root())}:{lineno}: wire code "
                    f"'{code}' is not registered in platform.core.errors.CATALOG"
                )
    assert not violations, (
        "WS error codes must be registered in the error CATALOG "
        "(the front-end error maps mirror it):\n" + "\n".join(violations)
    )


def test_ws_error_code_guard_self_check(tmp_path: Path) -> None:
    """The guard actually fires on a constructed unregistered code."""
    probe = tmp_path / "violation.py"
    probe.write_text(
        'def f(send):\n    await send("error", message="x", code="Z9999")\n',
        encoding="utf-8",
    )
    hits = _emitted_codes(probe)
    assert hits == [("Z9999", 2)]
