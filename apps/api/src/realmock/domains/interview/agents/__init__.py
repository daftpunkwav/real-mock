"""LLM interview execution chain: turn runner, session state, prompts, and tools.

This is the real agent loop of the interview domain (runner_opening / runner_turn /
runner_closing, tool rounds, follow-ups, verdicts). The turn state machine and media
pipeline live in :mod:`realtime`; silence-nudge templates live in
:mod:`realtime.nudge`; pluggable perception capabilities live in
:mod:`capabilities`.

External layers (``realtime``, ``routes``) must depend only on this facade plus
the event contract (:mod:`agents.events`, versioned via ``schema_version``) —
never on sibling modules directly. Internal modules keep importing each other
by submodule path.

The re-exports below are lazy (PEP 562): resolving them imports the owning
submodule on first use, so importing this package (or a leaf such as
``agents.workflows`` from ``process.planning``) never pulls the runner chain
at package-init time. Without this, ``plan_schema`` ↔ ``turn_output`` form a
package-level import cycle.
"""

from __future__ import annotations

from typing import Any

#: Facade name → owning submodule (relative). Resolved by ``__getattr__``.
_LAZY_EXPORTS: dict[str, str] = {
    "InterviewRunner": ".runner",
    "InterviewSessionState": ".session_state",
    "run_finish_lifecycle": ".finish_lifecycle",
    "strip_markers": ".agent_text",
    "strip_think_blocks": ".agent_text",
}

__all__ = [
    "InterviewRunner",
    "InterviewSessionState",
    "run_finish_lifecycle",
    "strip_markers",
    "strip_think_blocks",
]


def __getattr__(name: str) -> Any:
    """Lazily re-export facade names (see module docstring for why)."""
    if name in _LAZY_EXPORTS:
        from importlib import import_module

        return getattr(import_module(_LAZY_EXPORTS[name], __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
