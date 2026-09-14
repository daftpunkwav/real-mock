"""Turn layer mixin aggregation (coordinator + streaming + control)."""

from realmock.domains.interview.realtime.turn.coordinator import TurnCoordinatorMixin
from realmock.domains.interview.realtime.turn.control import TurnControlMixin
from realmock.domains.interview.realtime.turn.streaming import TurnStreamingMixin


class TurnStackMixin(
    TurnCoordinatorMixin,
    TurnStreamingMixin,
    TurnControlMixin,
):
    """Candidate turns, streaming consumption and interruption/closing."""


__all__ = ["TurnStackMixin"]
