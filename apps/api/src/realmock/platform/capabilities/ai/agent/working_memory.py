"""Agent working memory: stays in model-visible context after compression.

Aligns with Pi ``transformContext`` (assemble visible context each step) and
Codex's "session memory vs transcript" split: structured facts are stored
separately and do not depend on truncated verbatim dialogue.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

_MAX_LIST = 16
_ITEM_CHARS = 160

MEMORY_MARKER = "[Working memory]"
# Marker written by an older build; still recognized on load so history
# persisted before an upgrade is parsed instead of silently dropped.
LEGACY_MEMORY_MARKER = "[working memory]"


def _clip(text: str, n: int = _ITEM_CHARS) -> str:
    s = (text or "").strip().replace("\n", " ")
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def _bounded_append(items: list[str], value: str, limit: int = _MAX_LIST) -> None:
    v = _clip(value)
    if not v:
        return
    if v in items:
        return
    items.append(v)
    if len(items) > limit:
        del items[:-limit]


@dataclass
class WorkingMemory:
    """Per-session working memory (shared interview / prep shape; fields vary by domain)."""

    asked: list[str] = field(default_factory=list)
    weak_points: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    pending_quiz: str = ""

    @classmethod
    def from_state(cls, state: dict[str, Any] | None) -> WorkingMemory:
        raw = state or {}
        asked = [str(x) for x in (raw.get("asked_questions") or []) if x]
        weak = [str(x) for x in (raw.get("weak_points") or []) if x]
        findings: list[str] = []
        # github_* keeps its own trail; interview company/resume lookups share
        # company_findings so verified local knowledge survives compaction.
        for source in ("github_findings", "company_findings"):
            for f in raw.get(source) or []:
                if isinstance(f, dict):
                    findings.append(_clip(f"{f.get('tool', '')}: {f.get('preview', '')}"))
                elif f:
                    findings.append(_clip(str(f)))
        notes = [str(x) for x in (raw.get("memory_notes") or []) if x]
        quiz = str(raw.get("pending_quiz") or "")
        return cls(
            asked=asked[-_MAX_LIST:],
            weak_points=weak[-_MAX_LIST:],
            findings=findings[-_MAX_LIST:],
            notes=notes[-_MAX_LIST:],
            pending_quiz=_clip(quiz, 240),
        )

    def to_state_patch(self) -> dict[str, Any]:
        """Patch written back into agent_state (does not clear unrelated keys)."""
        patch: dict[str, Any] = {
            "asked_questions": list(self.asked),
            "weak_points": list(self.weak_points),
            "memory_notes": list(self.notes),
        }
        if self.pending_quiz:
            patch["pending_quiz"] = self.pending_quiz
        return patch

    def remember(self, kind: str, text: str) -> None:
        if kind == "asked":
            _bounded_append(self.asked, text)
        elif kind == "weak":
            _bounded_append(self.weak_points, text)
        elif kind == "finding":
            _bounded_append(self.findings, text)
        elif kind == "quiz":
            self.pending_quiz = _clip(text, 240)
        else:
            _bounded_append(self.notes, text)

    def absorb_omitted(self, omitted: list[dict[str, Any]], *, limit: int = 12) -> None:
        """Compress dropped dialogue into short notes so only counts are not retained."""
        lines: list[str] = []
        for m in omitted:
            role = m.get("role")
            if role not in ("user", "assistant"):
                continue
            content = m.get("content")
            if isinstance(content, list):
                texts = []
                for item in content:
                    if isinstance(item, dict) and item.get("text"):
                        texts.append(str(item["text"]))
                content = " ".join(texts)
            snippet = _clip(str(content or ""), 80)
            if snippet:
                lines.append(f"{role}:{snippet}")
            if len(lines) >= limit:
                break
        if lines:
            _bounded_append(self.notes, "Earlier dialogue summary: " + " | ".join(lines), limit=_MAX_LIST)

    def render(self) -> str:
        """Model-visible memory paragraph (without marker)."""
        parts: list[str] = []
        if self.asked:
            parts.append("Covered: " + "; ".join(self.asked[-8:]))
        if self.weak_points:
            parts.append("Weak spots: " + "; ".join(self.weak_points[-8:]))
        if self.findings:
            parts.append("Verified: " + "; ".join(self.findings[-5:]))
        if self.pending_quiz:
            parts.append("Pending quiz to review: " + self.pending_quiz)
        if self.notes:
            parts.append("Notes: " + "; ".join(self.notes[-6:]))
        return "\n".join(parts)

    def dump_block(self) -> str:
        """Persistable system block: JSON state + short model-visible text."""
        payload = json.dumps(self.to_state_patch(), ensure_ascii=False)
        rendered = self.render()
        body = payload if not rendered else f"{payload}\n{rendered}"
        return f"{MEMORY_MARKER}\n{body}"

    @classmethod
    def load_from_messages(cls, messages: list[dict[str, Any]]) -> WorkingMemory:
        for m in reversed(messages):
            if m.get("role") != "system":
                continue
            content = m.get("content")
            if not isinstance(content, str):
                continue
            # Accept the legacy marker during upgrades
            if not (
                content.startswith(MEMORY_MARKER)
                or content.startswith(LEGACY_MEMORY_MARKER)
            ):
                continue
            marker = (
                MEMORY_MARKER
                if content.startswith(MEMORY_MARKER)
                else LEGACY_MEMORY_MARKER
            )
            rest = content[len(marker):].lstrip("\n")
            first, _, _tail = rest.partition("\n")
            try:
                return cls.from_state(json.loads(first))
            except (json.JSONDecodeError, TypeError, ValueError):
                return cls()
        return cls()
