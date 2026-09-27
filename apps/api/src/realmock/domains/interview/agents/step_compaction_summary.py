"""Step-compaction content layer: verbatim transcript → structured brief.

Owns the transcript rendering, the summary LLM call and its parsing, the
rendered briefing block, competency-reflection recording into the cognitive
graph, and the rollup merge of aged briefings into a running digest. All
failure paths here are non-destructive: a failed call simply returns
``None``/no-op and the raw dialogue stays.

The state bookkeeping lives in :mod:`step_compaction_state`; the core
operation and its orchestration live in :mod:`step_compaction`.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from realmock.domains.interview.agents.agent_policies import COMPACT
from realmock.domains.interview.agents.memory.cognitive_graph import CompetencyStatus
from realmock.domains.interview.agents.step_compaction_prompts import (
    STEP_ROLLUP_PROMPT,
    STEP_SUMMARY_PROMPT,
)
from realmock.domains.interview.agents.step_compaction_state import steps_state

if TYPE_CHECKING:
    from realmock.domains.interview.agents.session_state import InterviewSessionState

logger = logging.getLogger(__name__)

_SUMMARY_KEYS = (
    "topics",
    "evidence",
    "verified",
    "suspicious",
    "weak_points",
    "agreed_facts",
    "probes_pending",
)


def render_transcript(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for m in messages:
        role = m.get("role")
        if role not in ("user", "assistant", "system"):
            continue
        content = m.get("content")
        text = content if isinstance(content, str) else _json_dumps(content)
        lines.append(f"[{role}] {text}")
    return "\n".join(lines)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _parse_summary(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not raw:
        return None
    if not any(isinstance(raw.get(k), list) and raw.get(k) for k in _SUMMARY_KEYS):
        return None  # empty/garbage summary counts as a failure
    return raw


def render_summary_block(step_no: int, summary: dict[str, Any]) -> str:
    def _items(key: str) -> str:
        value = summary.get(key) or []
        if isinstance(value, list):
            return "; ".join(_render_item(v) for v in value)
        return str(value)

    def _render_item(v: Any) -> str:
        if isinstance(v, dict):
            return _json_dumps(v)
        return str(v)

    lines = [f"## Step {step_no} summary (closed step briefing — do not repeat its questions)"]
    if summary.get("topics"):
        lines.append("Topics asked: " + _items("topics"))
    evidence = summary.get("evidence") or []
    if isinstance(evidence, list) and evidence:
        lines.append("Evidence:")
        for e in evidence:
            lines.append(f"  - {_json_dumps(e)}")
    for key, label in (
        ("verified", "Verified strengths"),
        ("suspicious", "Suspicious claims"),
        ("weak_points", "Weak points"),
        ("agreed_facts", "Agreed facts"),
        ("probes_pending", "Pending probes"),
    ):
        if summary.get(key):
            lines.append(f"{label}: {_items(key)}")
    if summary.get("pacing_note"):
        lines.append(f"Pacing note: {summary['pacing_note']}")
    return "\n".join(lines)


async def summarize_call(llm: Any, transcript: str, focus: str) -> dict[str, Any] | None:
    raw = await llm.chat_json(
        [
            {"role": "system", "content": STEP_SUMMARY_PROMPT},
            {
                "role": "user",
                "content": (
                    (f"Step focus: {focus}\n" if focus else "") + f"Step transcript:\n{transcript}"
                ),
            },
        ],
        temperature=0.2,
    )
    return _parse_summary(raw)


def apply_reflections(agent: "InterviewSessionState", summary: dict[str, Any]) -> None:
    """Record the summary's competency reflections into the cognitive graph.

    The structured brief carries a ``reflections`` list, so the per-step
    judgment rides the same call as the compaction instead of a separate
    periodic agent pass.
    """
    for ref in summary.get("reflections") or []:
        if not isinstance(ref, dict):
            continue
        topic = str(ref.get("topic", "")).strip()
        status = str(ref.get("status", "untested")).lower()
        if not topic or status not in {"verified", "suspicious", "failed", "untested"}:
            continue
        try:
            confidence = float(ref.get("confidence", 0.8))
        except (TypeError, ValueError):
            confidence = 0.8
        status_enum = (
            CompetencyStatus(status)
            if status in {s.value for s in CompetencyStatus}
            else CompetencyStatus.UNTESTED
        )
        agent.cognitive_memory.record_finding(
            topic=topic,
            category=str(ref.get("category", "general")),
            status=status_enum,
            claim=str(ref.get("claim", "")),
            finding=str(ref.get("finding", "")),
            turn_index=int(_steps_turn_index(agent)),
            confidence=confidence,
        )


def _steps_turn_index(agent: "InterviewSessionState") -> int:
    return len(agent.agent_state.get("asked_questions", []))


async def rollup(llm: Any, agent: "InterviewSessionState") -> None:
    steps = steps_state(agent)
    summaries: list[dict[str, Any]] = steps.get("summaries", [])
    keep = COMPACT.keep_recent_summaries
    retiring = summaries[:-keep] if len(summaries) > keep else []
    if not retiring:
        return
    existing = str(steps.get("interview_summary", "") or "")
    try:
        merged = await llm.chat(
            [
                {"role": "system", "content": STEP_ROLLUP_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Existing digest:\n{existing or '(empty — first merge)'}\n\n"
                        "Old step briefings to merge:\n"
                        + "\n\n".join(str(s.get("rendered", "")) for s in retiring)
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=2000,
        )
    except Exception as e:
        logger.debug("step rollup call failed; deferring: %s", e)
        return
    text = str(merged or "").strip()
    if not text:
        return
    steps["interview_summary"] = text
    steps["summaries"] = summaries[-keep:]
    steps["retired_count"] = int(steps.get("retired_count", 0)) + len(retiring)
    logger.info(
        "step summaries rolled up: retired=%d kept=%d", len(retiring), len(steps["summaries"])
    )
