"""Agent loop termination signal: The tool requires the loop to end immediately."""

from __future__ import annotations


class AgentHalt(Exception):
    """The tool requests immediate termination of the loop (for example, ask_user is waiting for user input).

    message is written back to the message sequence as the tool's observation,
    ensuring a one-to-one correspondence between assistant.tool_calls and tool results.
    """

    def __init__(self, observation: str = ""):
        super().__init__(observation or "agent halted by tool")
        self.observation = observation or "agent halted by tool"
