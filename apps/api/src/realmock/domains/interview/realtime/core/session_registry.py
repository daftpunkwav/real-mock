"""Single-session, single-connection lease registry for interview WebSockets.

Extracted from ``ws_handler``; ``WsConnectionRegistry`` encapsulates in-process state and exposes only
explicit methods, preventing a mutable module-level dict from becoming an implicit global dependency.

Deployment constraints (see deployment config):
- ``memory``: under a single worker / single instance, guarantees only one active WS per session.
- ``database``: the ``ws_session_leases`` table stores lease tokens; heartbeats validate the DB lease.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Protocol

from realmock.platform.config import get_settings
from realmock.platform.database import sessions_db_session

logger = logging.getLogger(__name__)


class SessionConnection(Protocol):
    """Leaseholder minimal interface (implemented by InterviewWSHandler)."""

    _superseded: bool

    @property
    def session_id(self) -> int: ...

    async def send(self, msg_type: str, **payload) -> None: ...

    @property
    def ws(self): ...


def _lease_token(handler: SessionConnection) -> str:
    token = getattr(handler, "lease_token", None)
    if token:
        return str(token)
    return str(id(handler))


def _persist_lease_sync(session_id: int, lease_token: str) -> None:
    from realmock.domains.interview.models import WsSessionLease

    with sessions_db_session() as db:
        try:
            row = db.query(WsSessionLease).filter(WsSessionLease.session_id == session_id).first()
            now = datetime.now(timezone.utc)
            if row is None:
                db.add(WsSessionLease(session_id=session_id, lease_token=lease_token, updated_at=now))
            else:
                row.lease_token = lease_token
                row.updated_at = now
            db.commit()
        except Exception:
            db.rollback()
            logger.debug("WS lease DB write failed session=%s", session_id, exc_info=True)


def _release_lease_sync(session_id: int, lease_token: str) -> None:
    from realmock.domains.interview.models import WsSessionLease

    with sessions_db_session() as db:
        try:
            row = (
                db.query(WsSessionLease)
                .filter(WsSessionLease.session_id == session_id)
                .filter(WsSessionLease.lease_token == lease_token)
                .first()
            )
            if row is not None:
                db.delete(row)
                db.commit()
        except Exception:
            db.rollback()
            logger.debug("WS lease DB release failed session=%s", session_id, exc_info=True)


def _db_lease_matches_sync(session_id: int, lease_token: str) -> bool:
    from realmock.domains.interview.models import WsSessionLease

    with sessions_db_session() as db:
        try:
            row = db.query(WsSessionLease).filter(WsSessionLease.session_id == session_id).first()
            if row is None:
                return False
            return row.lease_token == lease_token
        except Exception:
            logger.debug("WS lease verification failed session=%s", session_id, exc_info=True)
            return False


class WsConnectionRegistry:
    """In-process WS connection lease table (default for local singleton; database mode with DB heartbeat verification)."""

    def __init__(self) -> None:
        self._handlers: dict[int, SessionConnection] = {}
        self._lock = asyncio.Lock()

    async def _supersede_old(self, old: SessionConnection, session_id: int) -> None:
        old._superseded = True
        logger.info(
            "WS session lease is replaced session=%s old=%s new=%s",
            session_id,
            id(old),
            id(self._handlers.get(session_id)),
        )
        try:
            await old.send(
                "error",
                message="This interview is open in another window; this connection was superseded",
                code="B2003",
            )
        except Exception:
            logger.debug("WS replaces the connection to notify the old end of failure session=%s", session_id, exc_info=True)
        try:
            await old.ws.close(code=4000)
        except Exception:
            logger.debug("WS replaces the connection and fails to close the old end session=%s", session_id, exc_info=True)

    async def verify_lease(self, handler: SessionConnection) -> bool:
        """Verify the lease token in database mode; if it fails, it will be marked superseded."""
        cfg = get_settings()
        if cfg.ws_lease_backend != "database":
            return True
        token = _lease_token(handler)
        ok = await asyncio.to_thread(_db_lease_matches_sync, handler.session_id, token)
        if not ok:
            handler._superseded = True
        return ok

    async def claim(self, handler: SessionConnection) -> None:
        """Occupy the session lease for the handler; if there is an old connection, notify and close the old connection."""
        cfg = get_settings()
        token = _lease_token(handler)
        old: SessionConnection | None = None
        async with self._lock:
            old = self._handlers.get(handler.session_id)
            self._handlers[handler.session_id] = handler
            handler._superseded = False
        if cfg.ws_lease_backend == "database":
            await asyncio.to_thread(_persist_lease_sync, handler.session_id, token)
        if old is not None and old is not handler:
            await self._supersede_old(old, handler.session_id)

    async def release(self, handler: SessionConnection) -> None:
        """Only released if the handler still holds the lease (the replaced old connection must not accidentally delete the new connection)."""
        cfg = get_settings()
        token = _lease_token(handler)
        async with self._lock:
            if self._handlers.get(handler.session_id) is handler:
                self._handlers.pop(handler.session_id, None)
        if cfg.ws_lease_backend == "database":
            await asyncio.to_thread(_release_lease_sync, handler.session_id, token)

    def clear_for_tests(self) -> None:
        self._handlers.clear()

    def snapshot_for_tests(self) -> dict[int, SessionConnection]:
        return self._handlers


_registry: WsConnectionRegistry | None = None


def get_ws_connection_registry() -> WsConnectionRegistry:
    """Lazy singleton: tests can replace the instance via ``reset_ws_connection_registry``."""
    global _registry
    if _registry is None:
        _registry = WsConnectionRegistry()
    return _registry


def reset_ws_connection_registry(registry: WsConnectionRegistry | None = None) -> None:
    """For testing: clear or inject custom registry."""
    global _registry
    if registry is None:
        get_ws_connection_registry().clear_for_tests()
        _registry = WsConnectionRegistry()
    else:
        _registry = registry


# ── Module-level thin packaging (keep existing import paths)────────────────────────
async def verify_connection_lease(handler: SessionConnection) -> bool:
    """Check the handler still holds its session lease (single-tab guard)."""
    return await get_ws_connection_registry().verify_lease(handler)


async def claim_session_connection(handler: SessionConnection) -> None:
    """Take the session lease for a handler, evicting any previous holder."""
    await get_ws_connection_registry().claim(handler)


async def release_session_connection(handler: SessionConnection) -> None:
    """Release the lease only if still held by this handler."""
    await get_ws_connection_registry().release(handler)


def reset_session_registry_for_tests() -> None:
    reset_ws_connection_registry()


def active_handlers_for_tests() -> dict[int, SessionConnection]:
    return get_ws_connection_registry().snapshot_for_tests()
