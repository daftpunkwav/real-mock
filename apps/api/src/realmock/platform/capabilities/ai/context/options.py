"""Compaction policy model: intensity, directive, and retain window.

Neutral, domain-free value object shared by every compaction caller
(turn-start auto-compact, manual ``/compact``, agent-invoked compaction).
Callers pass one :class:`CompactionOptions`; validation rejects nothing —
:class:`CompactionOptions.resolve` normalizes garbage to safe defaults and
the HTTP layer enforces hard bounds (422) before it ever gets here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

#: Compression intensity levels (capability names, no vendor/product terms).
CompactionIntensity = Literal["light", "balanced", "aggressive"]

INTENSITY_LEVELS: tuple[str, str, str] = ("light", "balanced", "aggressive")

#: Minimum verbatim tail (messages) each intensity guarantees, before `retain`.
INTENSITY_FLOORS: dict[str, int] = {"light": 10, "balanced": 4, "aggressive": 0}

#: Summary verbosity guidance appended to the summarizer prompt per intensity.
INTENSITY_DETAIL_HINT: dict[str, str] = {
    "light": "Preserve detail: several lines per section, keep examples, figures, and error text.",
    "balanced": "One to two lines per section; drop pleasantries and repetition.",
    "aggressive": "Single terse line per section; keep only decisions, numbers, names, and open items.",
}

DEFAULT_INTENSITY = "balanced"
#: Agent-decided (auto) trigger as a fraction of the context window.
#: Deliberately late (harness-aligned): compaction must fire on real space
#: pressure, not on early occupancy — small-window models otherwise compact
#: every turn. Users needing earlier folds pick a fixed 50–90% share.
DEFAULT_AUTO_COMPACT_THRESHOLD = 0.8
#: Default verbatim tail when the caller supplies no retain value.
DEFAULT_RETAIN = 4
#: Upper bound for the retain window (absurd values would disable compaction silently).
MAX_RETAIN = 200
#: Upper bound for a user-supplied compression directive (HTTP layer rejects longer input).
MAX_DIRECTIVE_CHARS = 500


@dataclass(frozen=True)
class CompactionOptions:
    """Normalized compaction parameters for one compaction run."""

    intensity: str = DEFAULT_INTENSITY
    directive: str = ""
    retain: int = DEFAULT_RETAIN

    @classmethod
    def resolve(
        cls,
        *,
        intensity: Any = None,
        directive: Any = None,
        retain: Any = None,
        default: "CompactionOptions | None" = None,
    ) -> "CompactionOptions":
        """Normalize raw inputs; never raises, falls back to ``default`` per field."""
        base = default or cls()
        level = str(intensity or "").strip().lower()
        if level not in INTENSITY_FLOORS:
            level = base.intensity if base.intensity in INTENSITY_FLOORS else DEFAULT_INTENSITY
        if directive is None:
            text = base.directive
        elif isinstance(directive, str):
            text = directive.strip()[:MAX_DIRECTIVE_CHARS]
        else:
            text = base.directive
        count = base.retain
        try:
            if retain is not None and not isinstance(retain, bool):
                count = int(retain)
        except (TypeError, ValueError):
            count = base.retain
        if count < 0:
            count = base.retain
        if count > MAX_RETAIN:
            count = MAX_RETAIN
        return cls(intensity=level, directive=text, retain=count)

    def keep_window(self) -> int:
        """Verbatim tail size: user retain guarantee raised by the intensity floor."""
        return max(self.retain, INTENSITY_FLOORS.get(self.intensity, INTENSITY_FLOORS[DEFAULT_INTENSITY]))

    def detail_hint(self) -> str:
        """Verbosity guidance for the summarizer prompt."""
        return INTENSITY_DETAIL_HINT.get(self.intensity, INTENSITY_DETAIL_HINT[DEFAULT_INTENSITY])


__all__ = [
    "CompactionIntensity",
    "CompactionOptions",
    "DEFAULT_AUTO_COMPACT_THRESHOLD",
    "DEFAULT_INTENSITY",
    "DEFAULT_RETAIN",
    "INTENSITY_DETAIL_HINT",
    "INTENSITY_FLOORS",
    "INTENSITY_LEVELS",
    "MAX_DIRECTIVE_CHARS",
    "MAX_RETAIN",
]
