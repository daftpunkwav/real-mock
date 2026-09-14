"""Shared Agent kernel: loop, working memory, and context assembly.

Interviewers and prep coaches share this package; domain tools remain in their respective services.
"""

from realmock.platform.capabilities.ai.agent.events import (
    AgentEvent,
    OnAgentEvent,
    emit_agent_event,
)
from realmock.platform.capabilities.ai.agent.loop import LoopResult, run_agent_loop
from realmock.platform.capabilities.ai.agent.working_memory import MEMORY_MARKER, WorkingMemory

__all__ = [
    "AgentEvent",
    "LoopResult",
    "MEMORY_MARKER",
    "OnAgentEvent",
    "WorkingMemory",
    "emit_agent_event",
    "run_agent_loop",
]
