"""Agent progress-event contract: type, callback shape, safe emit.

``OnAgentEvent`` accepts sync or async callbacks; the loop and the emit
helper await whichever is returned. Emitters must never let a UI callback
failure break the Agent loop, so emission is guarded and only logged.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

AgentEvent = dict[str, Any]
OnAgentEvent = Callable[[AgentEvent], Awaitable[None] | None]


async def emit_agent_event(
    on_event: OnAgentEvent | None, event: AgentEvent
) -> None:
    """Deliver one progress event; callback failures are logged, never raised."""
    if on_event is None:
        return
    try:
        maybe = on_event(event)
        if maybe is not None:
            await maybe
    except Exception:
        logger.warning(
            "Agent event emit failed type=%s", event.get("type"), exc_info=True
        )


__all__ = ["AgentEvent", "OnAgentEvent", "emit_agent_event"]
