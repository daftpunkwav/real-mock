"""LLM interview execution chain: turn runner, session state, prompts, and tools.

This is the real agent loop of the interview domain (runner_opening / runner_turn /
runner_closing, tool rounds, follow-ups, verdicts). The turn state machine and media
pipeline live in :mod:`realtime`; silence-nudge templates live in
:mod:`realtime.nudge`; pluggable perception capabilities live in
:mod:`capabilities`.

File clusters (new files take the matching prefix; do NOT add subpackages
until a cluster passes ~400 lines in one file or gains 3+ files — see the
architecture test holding the seams):

- run: ``runner`` + ``runner_opening/turn/closing`` + ``finish_lifecycle``;
- rounds: ``tool_round_runner`` + ``tool_round_stream`` + ``tools`` + ``hint_answer`` + ``tool_guard``;
- prompts: ``agent_prompts`` + ``closing_prompts`` + ``prompt_assembler`` + ``session_prompt``;
- state: ``session_state`` + ``session_overrides`` + ``past_records`` + ``history_compaction``;
- protocol: ``turn_output`` (+ leaf contracts ``events`` / ``agent_text`` / ``workflows``);
- followup: ``followup`` + ``followup_inject``.

External layers (``realtime``, ``routes``, ``process``) must depend only on
this facade plus the leaf contracts below — never on sibling modules directly:

- ``agents.events`` — WS event contract (versioned via ``schema_version``);
- ``agents.workflows`` — phase SSOT (read-only data);
- ``agents.agent_text`` — text filters (pure functions).

Internal modules keep importing each other by submodule path.

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
    "generate_full_reference_hint": ".hint_answer",
    "run_finish_lifecycle": ".finish_lifecycle",
    "session_llm": ".session_overrides",
    "session_stt_credentials": ".session_overrides",
    "session_tts_credentials": ".session_overrides",
    "strip_markers": ".agent_text",
    "strip_think_blocks": ".agent_text",
}

__all__ = [
    "InterviewRunner",
    "InterviewSessionState",
    "generate_full_reference_hint",
    "run_finish_lifecycle",
    "session_llm",
    "session_stt_credentials",
    "session_tts_credentials",
    "strip_markers",
    "strip_think_blocks",
]


def __getattr__(name: str) -> Any:
    """Lazily re-export facade names (see module docstring for why)."""
    if name in _LAZY_EXPORTS:
        from importlib import import_module

        return getattr(import_module(_LAZY_EXPORTS[name], __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
