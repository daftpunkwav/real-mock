"""DeepReportAgent: two-stage ReAct pipeline over a frozen interview ledger.

Stage 1 runs per-batch turn-notes loops in parallel (bounded); stage 2 runs a
synthesis loop that reads the notes and produces the aligned verdict, scores,
highlights / key problems, and training plan. The transcript is only ever
pulled through tools, never pasted whole into a prompt.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from realmock.domains.records.agents.report.normalize import normalize_report_payload
from realmock.domains.records.agents.report.synthesis_agent import run_synthesis
from realmock.domains.records.agents.report.turn_notes_agent import run_turn_notes_batch
from realmock.domains.records.schemas.report import DebriefReport, TurnNote
from realmock.platform.capabilities.ai.agent import OnAgentEvent as OnEvent
from realmock.platform.capabilities.ai.agent.tools import (
    github_tool_specs,
    profile_from_orm,
    profile_tool_specs,
    resume_tool_specs,
    snapshot_from_payload,
)
from realmock.platform.database import api_db_session
from realmock.platform.services.candidate_read import (
    get_default_user_profile,
    get_resume_agent_payload,
    get_user_profile,
)

logger = logging.getLogger(__name__)

#: Turns per stage-1 batch; sized so one loop covers its batch comfortably.
TURNS_PER_BATCH = 12
#: Parallel stage-1 batches (LLM concurrency bound).
MAX_PARALLEL_BATCHES = 2
#: Wall-clock budget for the whole report generation.
REPORT_TIME_BUDGET_SECONDS = 480.0


def split_turn_ids(turn_ids: list[str], per_batch: int = TURNS_PER_BATCH) -> list[list[str]]:
    """Split ordered turn ids into batches (kept ordered)."""
    if not turn_ids:
        return []
    return [turn_ids[i : i + per_batch] for i in range(0, len(turn_ids), per_batch)]


def _turn_ids(ledger: dict[str, Any]) -> list[str]:
    turns = ledger.get("turns")
    if not isinstance(turns, list):
        return []
    ids = []
    for turn in turns:
        if isinstance(turn, dict):
            tid = str(turn.get("turn_id") or "").strip()
            if tid:
                ids.append(tid)
    return ids


def build_context_specs(resume_id: int | None, profile_id: int | None) -> list:
    """Resume / profile / GitHub tools so notes can ground reference answers."""
    specs: list = []
    with api_db_session() as api_db:
        if resume_id:
            payload = get_resume_agent_payload(api_db, resume_id)
            if payload is not None:
                specs.extend(resume_tool_specs(snapshot_from_payload(payload)))
        row = (
            get_user_profile(api_db, profile_id)
            if profile_id
            else get_default_user_profile(api_db)
        )
        if row is not None:
            specs.extend(profile_tool_specs(profile_from_orm(row)))
    specs.extend(github_tool_specs())
    return specs


class DeepReportAgent:
    """Orchestrates stage 1 + stage 2; emits progress events via ``on_event``."""

    def __init__(
        self,
        llm: Any,
        *,
        on_event: OnEvent | None = None,
        context_specs: list | None = None,
    ) -> None:
        self._llm = llm
        self._on_event = on_event
        # None = auto-build from resume/profile ids; [] = deliberately tool-less.
        self._context_specs = context_specs

    async def run(
        self,
        *,
        role: str,
        level: str,
        company: str,
        workflow_type: str = "technical",
        strictness: int = 3,
        interview_style: str = "deep_dive",
        ledger: dict[str, Any] | None = None,
        session_result: str | None = None,
        process_context: str = "",
        resume_id: int | None = None,
        profile_id: int | None = None,
    ) -> DebriefReport:
        """Generate the deep report; never holds a DB session across awaits."""
        ledger = ledger if isinstance(ledger, dict) else {}
        ids = _turn_ids(ledger)
        specs = (
            build_context_specs(resume_id, profile_id)
            if self._context_specs is None
            else self._context_specs
        )

        async def _generate() -> DebriefReport:
            batches = split_turn_ids(ids)
            notes = await self._run_batches(ledger, batches, role, level, company, specs)
            if self._on_event is not None:
                await self._on_event({"type": "stage", "stage": "synthesis", "status": "running"})
            payload = await run_synthesis(
                self._llm,
                ledger=ledger,
                notes=notes,
                role=role,
                level=level,
                company=company,
                workflow_type=workflow_type,
                strictness=strictness,
                interview_style=interview_style,
                session_result=session_result,
                process_context=process_context,
                context_specs=specs,
                on_event=self._on_event,
            )
            if payload is None:
                raise RuntimeError("report synthesis produced no payload")
            payload["turn_notes"] = notes
            report = normalize_report_payload(payload)
            return self._ensure_turn_coverage(report, ids)

        return await asyncio.wait_for(_generate(), timeout=REPORT_TIME_BUDGET_SECONDS)

    async def _run_batches(
        self,
        ledger: dict[str, Any],
        batches: list[list[str]],
        role: str,
        level: str,
        company: str,
        specs: list,
    ) -> list[dict[str, Any]]:
        semaphore = asyncio.Semaphore(MAX_PARALLEL_BATCHES)

        async def one(idx: int, turn_ids: list[str]) -> list[dict[str, Any]]:
            label = f"{idx + 1}/{len(batches)}"
            async with semaphore:
                try:
                    return await run_turn_notes_batch(
                        self._llm,
                        ledger=ledger,
                        turn_ids=turn_ids,
                        batch_label=label,
                        role=role,
                        level=level,
                        company=company,
                        context_specs=specs,
                        on_event=self._on_event,
                    )
                except Exception as e:
                    logger.exception("turn-notes batch %s failed: %s", label, e)
                    return []

        results = await asyncio.gather(*(one(i, b) for i, b in enumerate(batches)))
        notes: list[dict[str, Any]] = [n for batch in results for n in batch]
        # Keep transcript order stable for the report UI.
        order = {tid: i for i, tid in enumerate(_turn_ids(ledger))}
        notes.sort(key=lambda n: order.get(str(n.get("turn_id")), 1 << 30))
        return notes

    def _ensure_turn_coverage(self, report: DebriefReport, ids: list[str]) -> DebriefReport:
        """Pad missing turn ids so the schema stays complete (visible in logs)."""
        have = {n.turn_id for n in report.turn_notes}
        missing = [tid for tid in ids if tid not in have]
        if not missing:
            return report
        logger.info("report missing notes for %d turn(s); padding empties", len(missing))
        for tid in missing:
            report.turn_notes.append(TurnNote(turn_id=tid))
        return report


__all__ = [
    "DeepReportAgent",
    "MAX_PARALLEL_BATCHES",
    "REPORT_TIME_BUDGET_SECONDS",
    "TURNS_PER_BATCH",
    "build_context_specs",
    "split_turn_ids",
]
