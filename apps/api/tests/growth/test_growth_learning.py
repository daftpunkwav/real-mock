"""System growth memory unit test."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from realmock.domains.growth.services import learning as learning_mod
from realmock.domains.growth.services.learning import get_system_insights, record_interview_learning


def test_record_and_insights(tmp_path, monkeypatch):
    monkeypatch.setattr(learning_mod, "_memory_path", lambda: tmp_path / "sys.json")

    session = SimpleNamespace(
        id=42,
        role="Backend engineer",
        company="bytedance",
        overall_score=85,
        agent_state=json.dumps({
            "tool_trace": [{"tool": "github_get_readme"}],
            "weak_points": ["Cache consistency"],
            "followup_clues": ["vague", "missing_data", "vague"],
        }),
    )

    record_interview_learning(session, report={"weaknesses": ["System design"]})
    insights = get_system_insights()
    assert insights["company_session_counts"].get("bytedance") == 1
    # followup_category_hits now records the actual follow-up categories (from followup_clues).
    assert insights["followup_category_hits"].get("vague") == 2
    assert insights["followup_category_hits"].get("missing_data") == 1
    # Record tool call statistics separately in tool_call_counts
    assert insights["tool_call_counts"].get("github_get_readme") == 1
    assert any("Cache" in (p.get("point") or "") for p in insights["recent_probes"])
    assert Path(tmp_path / "sys.json").exists()


def test_learning_concurrent_rmw(tmp_path, monkeypatch):
    """Concurrent record_interview_learning writers must not lose updates (file lock RMW)."""
    monkeypatch.setattr(learning_mod, "_memory_path", lambda: tmp_path / "sys.json")

    def _one(i: int) -> None:
        session = SimpleNamespace(
            id=i,
            role="Backend",
            company="bytedance",
            overall_score=80,
            agent_state=json.dumps({"followup_clues": ["vague"], "weak_points": []}),
        )
        record_interview_learning(session)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_one, range(20)))

    insights = get_system_insights()
    assert insights["company_session_counts"].get("bytedance") == 20
