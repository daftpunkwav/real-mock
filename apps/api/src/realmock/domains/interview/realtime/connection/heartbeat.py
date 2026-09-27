"""WS heartbeat loop (mixin): idle timeout detection, server_ping, timeout disconnect."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from realmock.domains.interview.realtime.core.session_registry import verify_connection_lease

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)

_HEARTBEAT_TIMEOUT_SEC: float = 30.0
_HEARTBEAT_MAX_MISSES: int = 3
# Consecutive malformed-JSON frames tolerated before the room is torn
# down: one bad frame is a client glitch, a stream of them is a broken
# or hostile client burning lease checks, log volume, and error frames.
_HEARTBEAT_MAX_MALFORMED: int = 5


class HeartbeatMixin:
    """Idle heartbeat: If no message is received after a continuous timeout, it will prompt and disconnect."""

    ctx: "ConnectionContext"

    if TYPE_CHECKING:
        # Members provided by sibling mixins / the composed InterviewWSHandler.
        _superseded: bool

        @property
        def session_id(self): ...

        @property
        def ws(self): ...

        send: Callable[..., Coroutine[Any, Any, None]]

    async def next_message(self) -> dict[str, Any] | None:
        """Return the next message to dispatch; return None when the connection should end (timeout disconnect / replacement / exception).

        If the timeout count is below the limit, send server_ping and continue waiting; after ``_HEARTBEAT_MAX_MISSES`` consecutive
        timeouts, send an error event and end the loop.
        """
        miss_count = 0
        malformed_streak = 0
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
                    try:
                        await self.send(
                            "error",
                            message="Heartbeat timed out; connection closed",
                            code="B2002",
                            retryable=True,
                        )
                    except Exception:
                        # A vanished client is the expected cause of a heartbeat
                        # timeout: the notice failing to send must not turn the
                        # graceful disconnect into an exception path (same
                        # handling as the B2003 / B2004 notices below).
                        logger.debug(
                            "Heartbeat timeout notice failed to send session=%s",
                            self.ctx.session_id,
                            exc_info=True,
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
            except json.JSONDecodeError:
                # A malformed JSON frame must not tear down the whole room:
                # reject the frame and keep waiting. A sustained stream of
                # them is a broken/hostile client, though — bound it.
                malformed_streak += 1
                if malformed_streak >= _HEARTBEAT_MAX_MALFORMED:
                    logger.warning(
                        "WS malformed-frame limit reached session=%s count=%s",
                        self.ctx.session_id,
                        malformed_streak,
                    )
                    try:
                        await self.send(
                            "error",
                            message="Too many malformed frames; connection closed",
                            code="B2004",
                            retryable=True,
                        )
                    except Exception:
                        logger.debug(
                            "Malformed-frame notice failed to send session=%s",
                            self.ctx.session_id,
                            exc_info=True,
                        )
                    return None
                logger.warning("Malformed WS JSON frame session=%s", self.ctx.session_id)
                try:
                    await self.send(
                        "error",
                        message="Malformed message frame; ignored",
                        code="A0001",
                        retryable=True,
                    )
                except Exception:
                    logger.debug(
                        "Malformed-frame notice failed to send session=%s",
                        self.ctx.session_id,
                        exc_info=True,
                    )
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
            malformed_streak = 0
            return data
        return None


__all__ = [
    "HeartbeatMixin",
    "_HEARTBEAT_MAX_MALFORMED",
    "_HEARTBEAT_MAX_MISSES",
    "_HEARTBEAT_TIMEOUT_SEC",
]
