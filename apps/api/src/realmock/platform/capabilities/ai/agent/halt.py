"""Agent loop control signals raised by tools: terminate (:class:`AgentHalt`)
or pause mid-turn awaiting an out-of-band result (:class:`AgentPause`).
"""

from __future__ import annotations


class AgentHalt(Exception):
    """The tool requests immediate termination of the loop.

    message is written back to the message sequence as the tool's observation,
    ensuring a one-to-one correspondence between assistant.tool_calls and tool results.
    """

    def __init__(self, observation: str = ""):
        super().__init__(observation or "agent halted by tool")
        self.observation = observation or "agent halted by tool"


class AgentPause(Exception):
    """The tool pauses the loop mid-turn: the raised call stays OPEN (no tool
    result is appended) and the loop ends the segment; the result arrives from
    outside the loop (e.g. the user answers a dialog) and the caller resumes
    the same turn. ``observation`` is display-only (tool-step card) and never
    enters the model context.
    """

    def __init__(self, observation: str = ""):
        super().__init__(observation or "agent paused by tool")
        self.observation = observation or "agent paused by tool"
