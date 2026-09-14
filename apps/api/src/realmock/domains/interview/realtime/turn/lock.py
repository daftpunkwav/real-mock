"""Turn lock (WS mixin): candidate-turn acquisition/release and epoch validation.

Extracted from :mod:`...turn_coordinator`. Handles lock semantics only, not stream consumption or STT.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from realmock.domains.interview.realtime.core.context import ConnectionContext


class TurnLockMixin:
    """Turn lock: reject when ``closing``; reject when busy and the epoch is unchanged; release only the lock for this epoch."""

    ctx: "ConnectionContext"

    def _can_start_user_turn(self) -> bool:
        """Whether to allow starting a new candidate round (including taking over after interruption)."""
        if self.ctx.closing:
            return False
        if not self.ctx.turn_busy:
            return True
        return self.ctx.busy_epoch != self.ctx.stream_epoch

    def _begin_user_turn(self) -> int | None:
        """Occupies the round lock and binds the current epoch; returns None if not startable."""
        if not self._can_start_user_turn():
            return None
        epoch = self.ctx.stream_epoch
        self.ctx.turn_busy = True
        self.ctx.busy_epoch = epoch
        return epoch

    def _end_user_turn(self, epoch: int) -> None:
        """The lock is released only if it is still occupied by this round."""
        if self.ctx.busy_epoch == epoch:
            self.ctx.turn_busy = False


__all__ = ["TurnLockMixin"]
