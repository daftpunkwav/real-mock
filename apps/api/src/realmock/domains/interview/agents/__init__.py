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
"""

from realmock.domains.interview.agents.agent_text import strip_markers, strip_think_blocks
from realmock.domains.interview.agents.finish_lifecycle import run_finish_lifecycle
from realmock.domains.interview.agents.runner import InterviewRunner
from realmock.domains.interview.agents.session_state import InterviewSessionState

__all__ = [
    "InterviewRunner",
    "InterviewSessionState",
    "run_finish_lifecycle",
    "strip_markers",
    "strip_think_blocks",
]
