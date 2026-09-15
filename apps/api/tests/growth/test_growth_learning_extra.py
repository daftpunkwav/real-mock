"""Growth learning tests for src/realmock/domains/growth/services/learning.py.

Covers: corrupt-file recovery, _parse_agent_state branches (existing test_growth_learning.py kept)
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


@pytest.fixture(autouse=True)
def _growth_table(engine):
    from realmock.platform.database import SessionsBase
    import realmock.domains.growth.models.growth  # noqa: F401

    SessionsBase.metadata.create_all(bind=engine)
    yield


# ---- routes/router (59-67, 73-74) ----








# ---- ingest (29-31, 34-35, 50-51) ----










# ---- learning (73-75, 90, 96-97) ----


def test_learning_corrupt_file_and_parse_branches(tmp_path, monkeypatch) -> None:
    from realmock.domains.growth.services import learning as mod

    # Corrupt JSON file -> warning + default (73-75).
    monkeypatch.setattr(mod, "_memory_path", lambda: tmp_path / "sys.json")
    monkeypatch.setattr(mod, "_lock_path", lambda: tmp_path / "sys.json.lock")
    (tmp_path / "sys.json").write_text("not-json{", encoding="utf-8")
    sess = SimpleNamespace(id=1, company="Acme", role="BE", overall_score=80, agent_state={})
    mod.record_interview_learning(sess, agent_state={"followup_clues": ["x"]})
    assert (tmp_path / "sys.json").exists()

    # _parse_agent_state dict passthrough (90) and bad JSON (96-97).
    assert mod._parse_agent_state({"a": 1}) == {"a": 1}
    assert mod._parse_agent_state("") == {}
    assert mod._parse_agent_state("not-json") == {}
    assert mod._parse_agent_state(json.dumps(["not", "dict"])) == {}
