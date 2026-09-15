"""Semantic competency graph and cognitive memory structure for interviews.

Responsibilities:
- Maintain candidate competency nodes across technical and behavioral domains.
- Record structured evidence (turn reference, candidate claim, assessor finding).
- Provide serializable state and compact prompt rendering for agent context.
- Support status transitions: UNTESTED -> SUSPICIOUS / VERIFIED / FAILED.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class CompetencyStatus(str, Enum):
    """Assessment status of a candidate competency area."""
    UNTESTED = "untested"
    VERIFIED = "verified"
    SUSPICIOUS = "suspicious"
    FAILED = "failed"


@dataclass
class CompetencyEvidence:
    """Individual proof point or finding recorded during interview dialogue."""
    turn_index: int
    claim: str
    finding: str
    confidence: float = 0.8
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompetencyEvidence:
        try:
            turn_index = int(data.get("turn_index", 0))
        except (ValueError, TypeError):
            turn_index = 0
        try:
            confidence = float(data.get("confidence", 0.8))
        except (ValueError, TypeError):
            confidence = 0.8
        try:
            timestamp = float(data.get("timestamp", time.time()))
        except (ValueError, TypeError):
            timestamp = time.time()
        return cls(
            turn_index=turn_index,
            claim=str(data.get("claim", "")),
            finding=str(data.get("finding", "")),
            confidence=confidence,
            timestamp=timestamp,
        )


@dataclass
class CompetencyNode:
    """A specific skill or technical domain under evaluation."""
    topic: str
    category: str = "general"
    status: CompetencyStatus = CompetencyStatus.UNTESTED
    confidence: float = 0.0
    evidence: list[CompetencyEvidence] = field(default_factory=list)
    last_probe: str = ""

    def add_evidence(
        self,
        *,
        turn_index: int,
        claim: str,
        finding: str,
        status: CompetencyStatus,
        confidence: float,
    ) -> None:
        self.evidence.append(
            CompetencyEvidence(
                turn_index=turn_index,
                claim=claim,
                finding=finding,
                confidence=confidence,
            )
        )
        self.status = status
        self.confidence = confidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "category": self.category,
            "status": self.status.value,
            "confidence": self.confidence,
            "evidence": [e.to_dict() for e in self.evidence],
            "last_probe": self.last_probe,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompetencyNode:
        raw_status = data.get("status", CompetencyStatus.UNTESTED.value)
        try:
            status = CompetencyStatus(raw_status)
        except (ValueError, KeyError):
            status = CompetencyStatus.UNTESTED

        try:
            confidence = float(data.get("confidence", 0.0))
        except (ValueError, TypeError):
            confidence = 0.0

        evidence = [
            CompetencyEvidence.from_dict(e)
            for e in data.get("evidence", [])
            if isinstance(e, dict)
        ]

        return cls(
            topic=str(data.get("topic", "unspecified")),
            category=str(data.get("category", "general")),
            status=status,
            confidence=confidence,
            evidence=evidence,
            last_probe=str(data.get("last_probe", "")),
        )


@dataclass
class WorkingMemory:
    """Transient working memory for active turn reasoning and code scratchpad."""
    current_topic: str = ""
    active_question: str = ""
    pending_probes: list[str] = field(default_factory=list)
    active_code_task: str = ""
    candidate_code: str = ""
    last_test_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> WorkingMemory:
        if not data or not isinstance(data, dict):
            return cls()
        return cls(
            current_topic=str(data.get("current_topic", "")),
            active_question=str(data.get("active_question", "")),
            pending_probes=list(data.get("pending_probes", [])),
            active_code_task=str(data.get("active_code_task", "")),
            candidate_code=str(data.get("candidate_code", "")),
            last_test_output=str(data.get("last_test_output", "")),
        )


class CognitiveMemoryGraph:
    """Multi-layer cognitive memory holding working memory and the competency knowledge graph."""

    def __init__(
        self,
        nodes: dict[str, CompetencyNode] | None = None,
        working_memory: WorkingMemory | None = None,
    ) -> None:
        self.nodes: dict[str, CompetencyNode] = nodes or {}
        self.working_memory: WorkingMemory = working_memory or WorkingMemory()

    def get_or_create_node(self, topic: str, category: str = "general") -> CompetencyNode:
        key = topic.strip().lower()
        if key not in self.nodes:
            self.nodes[key] = CompetencyNode(topic=topic, category=category)
        return self.nodes[key]

    def record_finding(
        self,
        *,
        topic: str,
        category: str = "general",
        status: CompetencyStatus,
        claim: str,
        finding: str,
        turn_index: int,
        confidence: float = 0.85,
    ) -> None:
        node = self.get_or_create_node(topic, category)
        node.add_evidence(
            turn_index=turn_index,
            claim=claim,
            finding=finding,
            status=status,
            confidence=confidence,
        )

    def render_prompt_summary(self) -> str:
        """Render a compact summary for the interviewer agent prompt."""
        verified = [n for n in self.nodes.values() if n.status == CompetencyStatus.VERIFIED]
        suspicious = [n for n in self.nodes.values() if n.status == CompetencyStatus.SUSPICIOUS]
        failed = [n for n in self.nodes.values() if n.status == CompetencyStatus.FAILED]

        lines: list[str] = ["[Cognitive Competency Assessment]"]
        if verified:
            items = ", ".join(f"{n.topic} (conf={n.confidence:.1f})" for n in verified[:6])
            lines.append(f"- Verified Strengths: {items}")
        if suspicious:
            items = "; ".join(f"{n.topic}: {n.evidence[-1].finding}" for n in suspicious[-4:] if n.evidence)
            lines.append(f"- Suspicious / Ambiguous Areas (probe these): {items}")
        if failed:
            items = "; ".join(f"{n.topic}: {n.evidence[-1].finding}" for n in failed[-4:] if n.evidence)
            lines.append(f"- Confirmed Weaknesses / Blindspots: {items}")

        if self.working_memory.pending_probes:
            probes = "; ".join(self.working_memory.pending_probes[-3:])
            lines.append(f"- Shadow Evaluator Directives: {probes}")

        return "\n".join(lines) if len(lines) > 1 else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "working_memory": self.working_memory.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CognitiveMemoryGraph:
        if not data or not isinstance(data, dict):
            return cls()
        raw_nodes = data.get("nodes")
        nodes = (
            {k: CompetencyNode.from_dict(v) for k, v in raw_nodes.items() if isinstance(v, dict)}
            if isinstance(raw_nodes, dict)
            else {}
        )
        working_mem = WorkingMemory.from_dict(data.get("working_memory"))
        return cls(nodes=nodes, working_memory=working_mem)
