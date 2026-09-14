"""WS connection layer mixin aggregation (lifecycle + auth + heartbeat)."""

from realmock.domains.interview.realtime.connection.auth import ConnectionAuthMixin
from realmock.domains.interview.realtime.connection.heartbeat import HeartbeatMixin
from realmock.domains.interview.realtime.connection.lifecycle import ConnectionLifecycleMixin


class ConnectionStackMixin(
    ConnectionLifecycleMixin,
    ConnectionAuthMixin,
    HeartbeatMixin,
):
    """Connection establishment, authentication, heartbeat and main loop."""


__all__ = ["ConnectionStackMixin"]
