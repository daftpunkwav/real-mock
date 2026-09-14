"""Resume-only review-plan tool.

The model owns the step list (8-15 steps). The last step must be generating the
evaluation JSON. Steps whose evidence is independent may run in parallel mode;
the tool loop already executes same-round calls concurrently. Frontend renders
this plan as the live progress UI.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from realmock.domains.resume.schemas.limits import (
    REVIEW_MAX_PLAN_STEPS,
    REVIEW_MIN_PLAN_STEPS,
)
from realmock.platform.capabilities.ai.agent.tools.spec import ToolSpec

STATUSES = ("pending", "in_progress", "done", "skipped")
MODES = ("serial", "parallel")
# Frontend mirrors this in features/resume/reviewProgress.ts to hide plan
# bookkeeping from the timeline; rename both together.
PLAN_TOOL_PREFIX = "review_"
# Last-step titles must clearly mean "write the evaluation". Bare "json"/"report"
# is too wide (e.g. "Parse package.json").
_FINAL_STEP_RE = re.compile(
    r"(evaluat(?:e|ion)|verdict|conclusi(?:on|ve)|finali[sz]e|"
    r"(?:write|generate|emit)\s+(?:the\s+)?(?:evaluation|verdict|json)|"
    r"评分|评价|结论|裁定)",
    re.I,
)

OnPlanChange = Callable[[list[dict[str, Any]]], Awaitable[None] | None]


@dataclass
class ProcessStep:
    """One reviewer-owned plan step."""

    id: str
    title: str
    status: str = "pending"
    note: str = ""
    mode: str = "serial"

    def as_dict(self) -> dict[str, Any]:
        """Serialize the step (id/title/status/note/mode) for SSE payloads."""
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "note": self.note,
            "mode": self.mode,
        }


_UNESCAPED_U_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


def _decode_escapes(text: str) -> str:
    """Decode literal ``\\uXXXX`` sequences some models double-escape.

    Only the \\uXXXX form is touched; genuine backslashes and other escapes
    pass through unchanged.
    """

    def _one(match: re.Match[str]) -> str:
        code = int(match.group(1), 16)
        if 0xD800 <= code <= 0xDFFF:
            # Lone surrogate: keep it escaped, a raw surrogate would break
            # UTF-8 encoding downstream (SSE payloads).
            return match.group(0)
        return chr(code)

    return _UNESCAPED_U_RE.sub(_one, text)


@dataclass
class ReviewProcess:
    """Mutable plan. Not shared with prep/interview."""

    max_steps: int = REVIEW_MAX_PLAN_STEPS
    min_steps: int = REVIEW_MIN_PLAN_STEPS
    steps: list[ProcessStep] = field(default_factory=list)
    on_change: OnPlanChange | None = None

    def snapshot(self) -> list[dict[str, Any]]:
        """Return a detached copy of the current steps for event payloads."""
        return [step.as_dict() for step in self.steps]

    async def _notify(self) -> None:
        if self.on_change is None:
            return
        maybe = self.on_change(self.snapshot())
        if maybe is not None:
            await maybe

    def _parse_titles(self, raw: Any) -> list[str] | str:
        if not isinstance(raw, list) or not raw:
            return "review_set_plan requires a non-empty steps array of titles."
        titles: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                title = str(item.get("title") or item.get("name") or "").strip()
            else:
                title = str(item or "").strip()
            if title:
                titles.append(_decode_escapes(title)[:160])
        if not titles:
            return "Every step needs a non-empty title."
        if len(titles) < self.min_steps or len(titles) > self.max_steps:
            return (
                f"Plan has {len(titles)} steps; write {self.min_steps}-{self.max_steps} steps. "
                "Last step must be generating the evaluation JSON."
            )
        if not _FINAL_STEP_RE.search(titles[-1]):
            return (
                "The last step must be generating the evaluation JSON "
                "(title should mention evaluation / verdict / 评价). "
                "Do not add extra steps yourself; resubmit the plan."
            )
        return titles

    async def set_plan(self, titles: list[str]) -> str:
        """Replace the plan with fresh pending steps and notify watchers.

        Args:
            titles: Step titles (length already validated by ``_parse_titles``).

        Returns:
            JSON observation with ``ok`` and the new snapshot.
        """
        self.steps = [
            ProcessStep(id=str(index + 1), title=title)
            for index, title in enumerate(titles)
        ]
        await self._notify()
        return json.dumps({"ok": True, "steps": self.snapshot()}, ensure_ascii=False)

    async def update_step(self, step_id: str, status: str, note: str, mode: str = "serial") -> str:
        """Advance one step by id or title; the final step cannot be skipped.

        Args:
            step_id: Step id or exact title to update.
            status: New status (must be a member of STATUSES).
            note: Optional reviewer note (escape-decoded, capped at 240 chars).
            mode: Execution mode (must be a member of MODES).

        Returns:
            JSON observation with ``ok`` and the snapshot, or an ``error``
            object (invalid_status/invalid_mode/unknown_step/last_step_cannot_skip).
        """
        if status not in STATUSES:
            return json.dumps(
                {"error": "invalid_status", "allowed": list(STATUSES)},
                ensure_ascii=False,
            )
        if mode not in MODES:
            return json.dumps(
                {"error": "invalid_mode", "allowed": list(MODES)},
                ensure_ascii=False,
            )
        target = None
        for step in self.steps:
            if step.id == str(step_id).strip() or step.title == str(step_id).strip():
                target = step
                break
        if target is None:
            return json.dumps(
                {"error": "unknown_step", "steps": self.snapshot()},
                ensure_ascii=False,
            )
        if self.steps and target is self.steps[-1] and status == "skipped":
            return json.dumps(
                {
                    "error": "last_step_cannot_skip",
                    "message": "The last step generates the evaluation and cannot be skipped.",
                    "steps": self.snapshot(),
                },
                ensure_ascii=False,
            )
        target.status = status
        target.mode = mode
        if note:
            target.note = _decode_escapes(note)[:240]
        await self._notify()
        return json.dumps({"ok": True, "steps": self.snapshot()}, ensure_ascii=False)


_FALLBACK_EVALUATION_TITLE = "Generate evaluation JSON"


def plan_titles_from_tool_names(
    names: list[str],
    *,
    max_steps: int = REVIEW_MAX_PLAN_STEPS,
) -> list[str]:
    """Last-resort plan when the model never called ``review_set_plan``.

    Titles are English spellings of tool names. Live plans come from the model
    in the resume's language; display names for tools live in the web i18n catalog.
    The 8-step minimum does not apply here: a degenerate fallback with fewer
    steps beats no plan at all.
    """
    labels: list[str] = []
    seen: set[str] = set()
    budget = max(1, max_steps - 1)
    for name in names:
        if name.startswith(PLAN_TOOL_PREFIX):
            continue
        label = name.replace("_", " ")[:160]
        if not label or label in seen:
            continue
        seen.add(label)
        labels.append(label)
        if len(labels) >= budget:
            break
    labels.append(_FALLBACK_EVALUATION_TITLE)
    return labels


def process_tool_specs(process: ReviewProcess) -> list[ToolSpec]:
    """Bind plan tools to one ``ReviewProcess`` instance."""

    async def set_plan(args: dict[str, Any]) -> str:
        parsed = process._parse_titles(args.get("steps"))
        if isinstance(parsed, str):
            return json.dumps({"error": "invalid_plan", "message": parsed}, ensure_ascii=False)
        return await process.set_plan(parsed)

    async def update_step(args: dict[str, Any]) -> str:
        return await process.update_step(
            str(args.get("id") or args.get("step_id") or ""),
            str(args.get("status") or "done"),
            str(args.get("note") or ""),
            str(args.get("mode") or "serial"),
        )

    async def get_plan(args: dict[str, Any]) -> str:
        del args
        return json.dumps({"steps": process.snapshot()}, ensure_ascii=False)

    return [
        ToolSpec(
            name="review_set_plan",
            description=(
                f"Declare the review plan ({process.min_steps}-{process.max_steps} steps). "
                "Call this early. Write every step title in the resume's language. "
                "The last step MUST be generating the evaluation JSON. "
                "Keep it in sync with review_update_step as you work. "
                "Do not skip this tool."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ordered step titles; last one generates the evaluation JSON",
                    },
                },
                "required": ["steps"],
            },
            handler=set_plan,
        ),
        ToolSpec(
            name="review_update_step",
            description=(
                "Mark a plan step pending / in_progress / done / skipped, with an optional note. "
                "Set in_progress when you start a step and done/skipped when you finish it, "
                "so the live plan always shows what is executing. Steps whose evidence is "
                "independent may share mode=parallel; issue their tool calls together in one "
                "round and they execute concurrently."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Step id (1-based) or exact title"},
                    "status": {"type": "string", "enum": list(STATUSES)},
                    "note": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": list(MODES),
                        "description": "parallel = independent evidence, batched with peers",
                    },
                },
                "required": ["id", "status"],
            },
            handler=update_step,
        ),
        ToolSpec(
            name="review_get_plan",
            description="Read the current review plan and step statuses.",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=get_plan,
        ),
    ]


__all__ = [
    "PLAN_TOOL_PREFIX",
    "ReviewProcess",
    "plan_titles_from_tool_names",
    "process_tool_specs",
]
