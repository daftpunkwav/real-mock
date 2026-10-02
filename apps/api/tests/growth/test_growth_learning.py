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
        agent_state=json.dumps(
            {
                "tool_trace": [{"tool": "github_get_readme"}],
                "weak_points": ["Cache consistency"],
                "followup_clues": ["vague", "missing_data", "vague"],
            }
        ),
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


def test_learning_wrong_shape_file_normalized(tmp_path, monkeypatch):
    """Valid JSON of the wrong shape must degrade to defaults instead of
    poisoning later reads/writes with AttributeErrors."""
    monkeypatch.setattr(learning_mod, "_memory_path", lambda: tmp_path / "sys.json")
    (tmp_path / "sys.json").write_text(
        json.dumps(
            {
                "company_session_counts": "nope",
                "avg_scores_by_company": {"acme": {"sum": "x", "n": 0}},
                "effective_probes": [1, "two", {"point": "kept"}],
                "updated_at": 123,
            }
        ),
        encoding="utf-8",
    )

    session = SimpleNamespace(id=7, role="r", company="c", overall_score=80, agent_state=None)
    record_interview_learning(session)  # must not raise

    insights = get_system_insights()
    # The string-valued counter map was dropped; the new write starts clean.
    assert insights["company_session_counts"].get("c") == 1
    # Non-dict score entries are dropped; the new session's score lands.
    assert insights["avg_scores_by_company"].get("c") == 80.0
    # Only dict probes survive normalization.
    assert [p.get("point") for p in insights["recent_probes"]] == ["kept"]
