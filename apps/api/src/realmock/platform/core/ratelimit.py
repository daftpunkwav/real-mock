"""Lightweight in-process rate limiting (no external dependencies).

Design goals:

- Prevent one IP from issuing a short burst of DoS traffic to expensive endpoints (LLM calls, upload, analysis);
- In-memory counting with a sliding window is sufficient for a single process and local-first operation;
- Integrate with FastAPI through Depends injection so decorators do not break OpenAPI documentation.

Memory management: a background cleanup thread reclaims buckets idle for more than ``_BUCKET_TTL_SECONDS``,
preventing unbounded dictionary growth in long-running services.

.. warning::

    With multiple workers (``uvicorn --workers N``), each worker counts independently and the limit
    is effectively multiplied by N; use ratelimit_backend=database (or centralized storage such as Redis) if cross-worker consistency is required.

Proxy trust chain: use the first ``X-Forwarded-For`` segment only when ``request.client.host`` belongs to ``TRUSTED_PROXY_CIDRS``
(loopback only by default), preventing forged headers from bypassing rate limits.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request
from sqlalchemy.exc import IntegrityError

from realmock.platform import database
from realmock.platform.config import get_settings
from realmock.platform.core.errors import ApiBusinessError, get_spec
from realmock.platform.models import RateLimitBucket

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def SessionsSessionLocal() -> Session:
    """Indirection to ``database.SessionsSessionLocal``, resolved on first use.

    Importing that symbol directly runs the module's PEP 562 ``__getattr__`` at
    import time, which builds the engine before configuration has settled and
    pins a factory that ``reset_engines()`` can no longer replace. Tests patch
    this function.
    """
    return database.SessionsSessionLocal()


# Bucket idle recovery time window. No access after this time is considered recyclable.
_BUCKET_TTL_SECONDS = 600
_CLEANUP_INTERVAL_SECONDS = 120

# When TRUSTED_PROXY_CIDRS is not configured, only loopback addresses are trusted
_DEFAULT_TRUSTED_PROXY_NETS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
)


@dataclass
class _Bucket:
    timestamps: deque[float]
    last_access: float = 0.0

    def __post_init__(self) -> None:
        if self.last_access == 0.0:
            self.last_access = time.monotonic()


_LOCK = threading.Lock()
_BUCKETS: dict[tuple[str, str], _Bucket] = {}
_cleanup_started = False


def _trusted_proxy_nets() -> list[ipaddress._BaseNetwork]:
    """Resolve trusted proxy CIDR; empty configuration fallback loopback."""
    raw = get_settings().trusted_proxy_cidr_list
    if not raw:
        return list(_DEFAULT_TRUSTED_PROXY_NETS)
    nets: list[ipaddress._BaseNetwork] = []
    for cidr in raw:
        try:
            nets.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            continue
    return nets or list(_DEFAULT_TRUSTED_PROXY_NETS)


def _peer_is_trusted_proxy(peer: str) -> bool:
    """Determine whether the directly connected peer is a trusted proxy."""
    try:
        ip = ipaddress.ip_address(peer.strip("[]"))
    except ValueError:
        return False
    return any(ip in net for net in _trusted_proxy_nets())


def _resolve_client_ip(request: Request) -> str:
    """Resolve the client IP.

    - Use the first ``X-Forwarded-For`` entry only when ``request.client.host`` is within
      ``TRUSTED_PROXY_CIDRS`` (loopback by default);
    - Direct public or untrusted-LAN connections always use ``request.client.host`` to prevent spoofing.
    """
    peer = request.client.host if request.client else None
    fwd = request.headers.get("x-forwarded-for")
    if fwd and peer and _peer_is_trusted_proxy(peer):
        return fwd.split(",")[0].strip() or peer
    return peer or "unknown"


def _ensure_cleanup_thread() -> None:
    """Lazily start the background cleanup thread, at most once per process.

    Check and set the flag inside ``_LOCK`` so concurrent first calls do not each start a sweeper.
    """
    global _cleanup_started
    if _cleanup_started:
        return
    with _LOCK:
        if _cleanup_started:
            return
        _cleanup_started = True

        def _sweep() -> None:
            while True:
                time.sleep(_CLEANUP_INTERVAL_SECONDS)
                cutoff = time.monotonic() - _BUCKET_TTL_SECONDS
                with _LOCK:
                    stale = [k for k, b in _BUCKETS.items() if b.last_access < cutoff]
                    for k in stale:
                        _BUCKETS.pop(k, None)

        t = threading.Thread(target=_sweep, name="ratelimit-sweeper", daemon=True)
    # Start the thread outside the lock and shorten the critical section
    t.start()


def _use_db_ratelimit() -> bool:
    return get_settings().ratelimit_backend == "database"


def _check_rate_limit_db_once(
    *,
    bucket_key: tuple[str, str],
    limit: int,
    window_seconds: int,
) -> None:
    key_str = f"{bucket_key[0]}:{bucket_key[1]}"
    # The DB backend must be read across processes/machine restarts (memory backend uses monotonic for a single process).
    # Timestamps must use the wall-clock epoch; a monotonic clock has no shared reference point for alignment with a new clock after a restart
    now = time.time()
    db = SessionsSessionLocal()
    try:
        row = db.query(RateLimitBucket).filter(RateLimitBucket.bucket_key == key_str).first()
        if row is None:
            row = RateLimitBucket(bucket_key=key_str, timestamps_json="[]")
            db.add(row)
        try:
            stamps = json.loads(row.timestamps_json or "[]")
            if not isinstance(stamps, list):
                stamps = []
        except (json.JSONDecodeError, TypeError):
            stamps = []
        stamps = [float(t) for t in stamps if isinstance(t, (int, float))]
        stamps = [t for t in stamps if t > now - window_seconds]
        if len(stamps) >= limit:
            retry_after = max(1, int(window_seconds - (now - stamps[0])))
            raise ApiBusinessError(
                get_spec("A0002"),
                message=f"The request is too frequent, please try again after {retry_after}s",
                headers={"Retry-After": str(retry_after)},
            )
        stamps.append(now)
        row.timestamps_json = json.dumps(stamps)
        db.commit()
    except ApiBusinessError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.debug("Database current limit write failed key=%s", key_str, exc_info=True)
        raise
    finally:
        db.close()


def _check_rate_limit_db(
    *,
    bucket_key: tuple[str, str],
    limit: int,
    window_seconds: int,
) -> None:
    """Check the current limit (DB backend), retrying once on a first-write race.

    ``bucket_key`` is the primary key, so two processes checking an unseen
    bucket concurrently both try to insert and one commit fails with
    ``IntegrityError``; re-reading once turns that transient race into a
    normal count instead of a 500.
    """
    for attempt in range(2):
        try:
            _check_rate_limit_db_once(
                bucket_key=bucket_key, limit=limit, window_seconds=window_seconds
            )
            return
        except IntegrityError:
            if attempt == 1:
                raise


def _check_rate_limit_memory(
    *,
    bucket_key: tuple[str, str],
    limit: int,
    window_seconds: int,
) -> None:
    """In-process sliding-window check, shared by request-IP and client-id keys."""
    _ensure_cleanup_thread()
    now = time.monotonic()
    with _LOCK:
        bucket = _BUCKETS.get(bucket_key)
        if bucket is None:
            bucket = _Bucket(timestamps=deque())
            _BUCKETS[bucket_key] = bucket
        # Drop timestamps outside the sliding window
        while bucket.timestamps and bucket.timestamps[0] <= now - window_seconds:
            bucket.timestamps.popleft()
        if len(bucket.timestamps) >= limit:
            retry_after = max(1, int(window_seconds - (now - bucket.timestamps[0])))
            raise ApiBusinessError(
                get_spec("A0002"),
                message=f"The request is too frequent, please try again after {retry_after}s",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.timestamps.append(now)
        bucket.last_access = now


def check_rate_limit(
    request: Request,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    """Check the current limit and throw ``ApiBusinessError(A0002, 429)`` when it exceeds the limit."""
    ip = _resolve_client_ip(request)
    bucket_key = (key, ip)
    if _use_db_ratelimit():
        _check_rate_limit_db(bucket_key=bucket_key, limit=limit, window_seconds=window_seconds)
        return
    _check_rate_limit_memory(bucket_key=bucket_key, limit=limit, window_seconds=window_seconds)


def check_rate_limit_by_id(
    *,
    key: str,
    client_id: str,
    limit: int,
    window_seconds: int = 60,
) -> None:
    """Rate-limit by any client_id (such as session_id); raise ``ApiBusinessError(A0002, 429)`` when the limit is exceeded.

    Allows paths without a ``Request``, such as WebSocket, to reuse the same sliding-window implementation.
    """
    bucket_key = (key, client_id or "unknown")
    if _use_db_ratelimit():
        _check_rate_limit_db(
            bucket_key=bucket_key, limit=limit, window_seconds=window_seconds
        )
        return
    _check_rate_limit_memory(bucket_key=bucket_key, limit=limit, window_seconds=window_seconds)


def try_rate_limit_by_id(
    *,
    key: str,
    client_id: str,
    limit: int,
    window_seconds: int = 60,
) -> bool:
    """WS-friendly encapsulation: Return False if the limit is exceeded, and no exception will be thrown."""
    try:
        check_rate_limit_by_id(
            key=key,
            client_id=client_id,
            limit=limit,
            window_seconds=window_seconds,
        )
        return True
    except HTTPException:
        return False


def rate_limit_dep(*, key: str, limit: int, window_seconds: int = 60):
    """Returns the current limiting Depends callback that can be hooked to FastAPI ``dependencies=``."""

    def _dep(request: Request) -> None:
        check_rate_limit(
            request, key=key, limit=limit, window_seconds=window_seconds
        )

    return _dep


def reset_rate_limit(key: str | None = None) -> None:
    """Clear current limit status, only for testing."""
    with _LOCK:
        if key is None:
            _BUCKETS.clear()
        else:
            for k in list(_BUCKETS.keys()):
                if k[0] == key:
                    _BUCKETS.pop(k, None)
