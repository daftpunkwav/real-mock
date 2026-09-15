"""Turn-tools tests for realmock.domains.prep.agents.turn_tools.

Covers: freeze_turn_tools bad-item tolerance and expand_turn_tools edges
Conventions: No LLM; TurnState only; rate limits reset per test
"""
from __future__ import annotations
import pytest

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()

def test_freeze_turn_tools_tolerates_bad_items(monkeypatch) -> None:
    import realmock.domains.prep.agents.turn_tools as turn_mod
    from realmock.domains.prep.agents.turn_state import TurnState

    st = TurnState()
    defs = turn_mod.freeze_turn_tools(resume_id=None, user_text="hi", turn_state=st)
    assert any("compact_context" in str(d) for d in defs)

    monkeypatch.setattr(
        turn_mod, "DOMAIN_TOOL_DEFINITIONS", ["bad-string", {"function": {"name": ""}}]
    )
    st2 = TurnState()
    defs2 = turn_mod.freeze_turn_tools(resume_id=None, user_text="hi", turn_state=st2)
    assert any("compact_context" in str(d) for d in defs2)

def test_expand_turn_tools_edge_branches() -> None:
    from realmock.domains.prep.agents.turn_state import TurnState
    from realmock.domains.prep.agents.turn_tools import expand_turn_tools, freeze_turn_tools

    st = TurnState()
    st.tools = None
    assert expand_turn_tools(turn_state=st, selected=["github_get_file"]) == []

    st2 = TurnState()
    st2.tools = ["bad-string"]
    added = expand_turn_tools(turn_state=st2, selected=["github_get_file"])
    assert added == ["github_get_file"]

    # Already present or unknown names are skipped (clean toolset builds present ok).
    st3 = TurnState()
    freeze_turn_tools(resume_id=None, user_text="hi", turn_state=st3)
    assert st3.tools is not None
    added2 = expand_turn_tools(turn_state=st3, selected=["unknown_xyz"])
    assert added2 == []
    added3 = expand_turn_tools(turn_state=st3, selected=["github_get_file"])
    assert added3 == ["github_get_file"]
    added4 = expand_turn_tools(turn_state=st3, selected=["github_get_file"])
    assert added4 == []
