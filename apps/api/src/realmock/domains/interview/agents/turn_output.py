"""Semantic parsing of interview-turn output: protocol control fields → strongly typed defaults.

For the mechanism layer (say-first streaming extraction), see :mod:`realmock.platform.capabilities.ai.llm.say_first_stream`;
this module only validates the control dict into strong types and fills defaults—any missing field/type drift
degrades only that field and does not affect the say voice channel.

``wait_seconds`` semantics: 0 means the model did not provide a value, so the consumer uses the default for the question type/phase;
all other values are clamped to 0-60 (silence-nudge window: the consumer clamps the lower bound to 7s; a closing turn does not need to wait).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from realmock.domains.interview.process.planning.plan_schema import (
    STEP_FOCUS_MAX_CHARS,
    STEP_QUESTIONS_MAX,
    STEP_TITLE_MAX_CHARS,
)

logger = logging.getLogger(__name__)

_PROTOCOL_VERSION = 1
_EMOTIONS = ("neutral", "smile", "serious")
_SOURCE_VALUES = ("resume", "github", "company_kb", "none")
_VERDICT_VALUES = ("passed", "failed")
_WAIT_MAX = 60
# Single source for step-field clamps: planning.plan_schema.
_PLAN_OPS_MAX_INSERTS = 3


@dataclass(frozen=True)
class TurnScore:
    """Instant brief comments on the candidates’ answers in the previous round (for reuse in the next round of prompts and reports)."""

    brief: str = ""
    rating: int = 0          # 1-5; 0=not provided
    weak_points: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TurnOutput:
    """Structured output of a round."""

    say: str = ""
    protocol_version: int = 0
    wait_seconds: int = 0
    emotion: str = "neutral"
    phase_complete: bool = False
    interview_complete: bool = False
    turn_score: TurnScore | None = None
    probe: str | None = None
    sources: tuple[str, ...] = ()
    verdict: str | None = None  # "passed" | "failed"; set on the wrap-up turn
    # Dynamic flow maintenance: sanitized {"title","focus","max_questions","kind"}
    # steps to insert after the current one (empty tuple = no-op).
    plan_ops: tuple[dict, ...] = ()
    degraded: bool = False   # True=no structured control area obtained (all default values)


def parse_turn_output(
    controls: dict | None,
    *,
    say_text: str,
    degraded: bool = False,
) -> TurnOutput:
    """Control dict → TurnOutput; type drift field-by-field pocket defaults, only records logs and does not throw errors."""
    if not isinstance(controls, dict):
        return TurnOutput(say=say_text, degraded=True)

    version = controls.get("v")
    if not isinstance(version, int) or isinstance(version, bool):
        version = 0

    wait_seconds = controls.get("wait_seconds")
    if isinstance(wait_seconds, bool) or not isinstance(wait_seconds, int):
        wait_seconds = 0
    elif wait_seconds < 0:
        wait_seconds = 0
    elif wait_seconds > _WAIT_MAX:
        wait_seconds = _WAIT_MAX

    emotion = controls.get("emotion")
    if emotion not in _EMOTIONS:
        emotion = "neutral"

    phase_complete = controls.get("phase_complete") is True
    interview_complete = controls.get("interview_complete") is True

    turn_score = _parse_turn_score(controls.get("turn_score"))

    probe = controls.get("probe")
    if probe is not None:
        probe = str(probe).strip()[:200] or None

    sources = _parse_sources(controls.get("sources"))

    verdict = controls.get("verdict")
    if verdict not in _VERDICT_VALUES:
        verdict = None

    plan_ops = _parse_plan_ops(controls.get("plan_ops"))

    if version != _PROTOCOL_VERSION:
        logger.debug("Round output protocol version v=%s (currently %s)", version, _PROTOCOL_VERSION)

    return TurnOutput(
        say=say_text,
        protocol_version=version,
        wait_seconds=wait_seconds,
        emotion=emotion,
        phase_complete=phase_complete,
        interview_complete=interview_complete,
        turn_score=turn_score,
        probe=probe,
        sources=sources,
        verdict=verdict,
        plan_ops=plan_ops,
        degraded=degraded,
    )


def _parse_plan_ops(raw: object) -> tuple[dict, ...]:
    """Sanitize model-provided plan insertions; unusable input degrades to no-op."""
    if not isinstance(raw, dict):
        return ()
    inserts = raw.get("insert_after_current")
    if not isinstance(inserts, list):
        return ()
    out: list[dict] = []
    for item in inserts[:_PLAN_OPS_MAX_INSERTS]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()[:STEP_TITLE_MAX_CHARS]
        if not title:
            continue
        focus = str(item.get("focus") or "").strip()[:STEP_FOCUS_MAX_CHARS] or title
        max_q = item.get("max_questions")
        if isinstance(max_q, bool) or not isinstance(max_q, int) or max_q < 1:
            max_q = 3
        max_q = min(max_q, STEP_QUESTIONS_MAX)
        out.append({
            "title": title,
            "focus": focus,
            "max_questions": max_q,
            "kind": str(item.get("kind") or "").strip()[:30],
        })
    return tuple(out)


def _parse_turn_score(raw: object) -> TurnScore | None:
    """turn_score shape check: non-dict → None; fields are defaulted one by one."""
    if not isinstance(raw, dict):
        return None
    brief = str(raw.get("brief") or "").strip()[:200]
    rating = raw.get("rating")
    if isinstance(rating, bool) or not isinstance(rating, int):
        rating = 0
    rating = max(0, min(5, rating))
    points_raw = raw.get("weak_points")
    points: list[str] = []
    if isinstance(points_raw, list):
        for p in points_raw[:2]:
            text = str(p or "").strip()[:120]
            if text:
                points.append(text)
    if not brief and not rating and not points:
        return None
    return TurnScore(brief=brief, rating=rating, weak_points=tuple(points))


def _parse_sources(raw: object) -> tuple[str, ...]:
    """sources whitelist filtering; unknown values ​​are discarded and empty sets are considered empty."""
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    for item in raw[:4]:
        value = str(item or "").strip().lower()
        if value in _SOURCE_VALUES and value not in out:
            out.append(value)
    return tuple(out)


__all__ = ["TurnOutput", "TurnScore", "parse_turn_output"]
