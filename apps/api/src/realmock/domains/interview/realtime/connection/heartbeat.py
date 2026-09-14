"""WS heartbeat loop (mixin): idle timeout detection, server_ping, timeout disconnect."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from realmock.domains.interview.realtime.core.session_registry import verify_connection_lease

if TYPE_CHECKING:
    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)

_HEARTBEAT_TIMEOUT_SEC: float = 30.0
_HEARTBEAT_MAX_MISSES: int = 3


class HeartbeatMixin:
    """Idle heartbeat: If no message is received after a continuous timeout, it will prompt and disconnect."""

    ctx: "ConnectionContext"

    async def next_message(self) -> dict[str, Any] | None:
        """Return the next message to dispatch; return None when the connection should end (timeout disconnect / replacement / exception).

        If the timeout count is below the limit, send server_ping and continue waiting; after ``_HEARTBEAT_MAX_MISSES`` consecutive
        timeouts, send an error event and end the loop.
        """
        miss_count = 0
        while not self.ctx.superseded:
            if not await verify_connection_lease(self):
                try:
                    await self.send(
                        "error",
                        message="This interview is open in another window; this connection is no longer valid",
                        code="B2003",
                    )
                except Exception:
                    logger.debug(
                        "Lease expiry notification failed to be sent session=%s",
                        self.ctx.session_id,
                        exc_info=True,
                    )
                return None
            try:
                data = await asyncio.wait_for(
                    self.ctx.ws.receive_json(),
                    timeout=_HEARTBEAT_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                if self.ctx.superseded:
                    return None
                miss_count += 1
                if miss_count >= _HEARTBEAT_MAX_MISSES:
                    logger.warning(
                        "WS heartbeat timeout disconnect session=%s miss=%s",
                        self.ctx.session_id, miss_count,
                    )
                    await self.send(
                        "error",
                        message="Heartbeat timed out; connection closed",
                        code="B2002",
                        retryable=True,
                    )
                    return None
                try:
                    await self.send("server_ping", t=int(asyncio.get_event_loop().time() * 1000))
                except Exception:
                    logger.debug(
                        "Heartbeat server_ping failed to send session=%s",
                        self.ctx.session_id,
                        exc_info=True,
                    )
                    return None
                continue
            except Exception:
                logger.debug(
                    "WS packet receiving exception session=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )
                return None
            if self.ctx.superseded:
                return None
            return data
        return None


__all__ = ["HeartbeatMixin", "_HEARTBEAT_TIMEOUT_SEC", "_HEARTBEAT_MAX_MISSES"]
