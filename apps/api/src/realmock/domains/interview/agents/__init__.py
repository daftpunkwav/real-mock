"""LLM interview agents: the lead interviewer plus every auxiliary role.

One role per subpackage, shared machinery flat at the package root:

- ``interviewer/`` — lead interviewer (opening / turn / closing streams);
- ``topology/`` — shadow evaluator, coding examiner, process orchestrator;
- ``hint/`` — reference-answer agent;
- ``planning/`` — flow-plan and HR round-program planners;
- ``research/`` — company web research + setup-page brief;
- ``memory/`` — cognitive memory graph.

Shared kernel (import each other by submodule path, cluster prefixes):

- protocol: ``events`` (leaf contract) + ``agent_text`` (leaf contract) + ``turn_output`` + ``say_first``;
- state: ``session_state`` + ``session_overrides`` + ``past_records`` + ``history_compaction``;
- prompts: ``agent_prompts`` + ``closing_prompts`` + ``prompt_assembler`` + ``session_prompt``;
- rounds: ``tool_round_runner`` + ``tool_round_stream`` + ``tools`` + ``tool_guard``;
- turn: ``followup`` + ``followup_inject`` + ``finish_lifecycle``.

The turn state machine and media pipeline live in :mod:`realtime`;
silence-nudge templates live in :mod:`realtime.nudge`; pluggable perception
capabilities live in :mod:`capabilities`; the phase SSOT lives at
:mod:`realmock.domains.interview.workflows` (domain root).

External layers (``realtime``, ``routes``, ``process``) must depend only on
this facade plus the two leaf contracts below — never on sibling modules
directly:

- ``agents.events`` — WS event contract (versioned via ``schema_version``);
- ``agents.agent_text`` — text filters (pure functions).

Internal modules keep importing each other by submodule path.

The re-exports below are lazy (PEP 562): resolving them imports the owning
submodule on first use, so importing this package never pulls the runner
chain at package-init time, and package-internal consumers that fetch shared
names through the package root (``planning.planner`` → ``session_llm``)
cannot force an import order on the flat modules during init.
"""

from __future__ import annotations

from typing import Any

#: Facade name → owning submodule (relative). Resolved by ``__getattr__``.
_LAZY_EXPORTS: dict[str, str] = {
    "InterviewRunner": ".interviewer.runner",
    "InterviewSessionState": ".session_state",
    "clear_company_briefs": ".research.company_brief",
    "generate_full_reference_hint": ".hint.hint_answer",
    "generate_plan_for_session": ".planning.planner",
    "generate_round_plan_for_process": ".planning.round_planner",
    "get_or_create_brief": ".research.company_brief",
    "run_finish_lifecycle": ".finish_lifecycle",
    "session_llm": ".session_overrides",
    "session_stt_credentials": ".session_overrides",
    "session_tts_credentials": ".session_overrides",
    "voice_prompt_directive": ".session_overrides",
    "strip_markers": ".agent_text",
    "strip_think_blocks": ".agent_text",
}

__all__ = [
    "InterviewRunner",
    "InterviewSessionState",
    "clear_company_briefs",
    "generate_full_reference_hint",
    "generate_plan_for_session",
    "generate_round_plan_for_process",
    "get_or_create_brief",
    "run_finish_lifecycle",
    "session_llm",
    "session_stt_credentials",
    "session_tts_credentials",
    "voice_prompt_directive",
    "strip_markers",
    "strip_think_blocks",
]


def __getattr__(name: str) -> Any:
    """Lazily re-export facade names (see module docstring for why)."""
    if name in _LAZY_EXPORTS:
        from importlib import import_module

        return getattr(import_module(_LAZY_EXPORTS[name], __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
