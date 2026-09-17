"""Phase SSOT lock: workflows PhaseDef ↔ InterviewPhaseId ↔ frontend phases.ts."""

from __future__ import annotations

import re
from pathlib import Path

from realmock.domains.interview.constants import InterviewPhaseId
from realmock.domains.interview.workflows import WORKFLOWS, phase_label_map, technical_phase_order


ROOT = Path(__file__).resolve().parents[4]  # repo root (tests/interview/ -> apps/api -> apps -> repo)
FRONTEND_PHASES = ROOT / "apps" / "web" / "src" / "config" / "phases.ts"


def test_all_phase_defs_use_known_ids() -> None:
    known = {m.value for m in InterviewPhaseId}
    used: set[str] = set()
    for wf in WORKFLOWS.values():
        for p in wf.phases:
            assert p.id in known, f"unknown phase id {p.id} (workflow={wf.id})"
            used.add(p.id)
    unused = known - used
    assert not unused, f"InterviewPhaseId unused: {unused}"


def test_technical_phase_order_single_source() -> None:
    assert list(technical_phase_order()) == [p.id for p in WORKFLOWS["technical"].phases]


def test_frontend_phase_order_matches_technical() -> None:
    text = FRONTEND_PHASES.read_text(encoding="utf-8")
    m = re.search(
        r"export const PHASE_ORDER[^=]*=\s*\[([^\]]+)\]",
        text,
        re.DOTALL,
    )
    assert m, "failed to parse frontend PHASE_ORDER"
    ids = re.findall(r'"([a-z_]+)"', m.group(1))
    assert tuple(ids) == technical_phase_order()


def test_frontend_phase_labels_cover_technical() -> None:
    text = FRONTEND_PHASES.read_text(encoding="utf-8")
    labels = phase_label_map()
    for pid in technical_phase_order():
        # Frontend map must include each technical phase with English label matching backend
        assert f"{pid}:" in text or f'"{pid}"' in text
        assert labels[pid]
        assert labels[pid] in text, f"frontend missing label {pid}={labels[pid]}"
