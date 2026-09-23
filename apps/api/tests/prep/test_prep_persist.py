"""Persist tests for realmock.domains.prep.agents.persist.

Covers: compaction_event, _summary_markers and persist_cancel never-raise path
Conventions: No real DB/LLM; finalize faked to fail; rate limits reset per test
"""
from __future__ import annotations
from types import SimpleNamespace
import pytest

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()

def test_compaction_event_reports_summary(monkeypatch) -> None:
    from realmock.domains.prep.agents.persist import compaction_event
    from realmock.platform.capabilities.ai.context.compress import COMPACTION_SUMMARY_MARKER

    before = [{"role": "user", "content": "hello"}]
    after = [
        {"role": "user", "content": "hello"},
        {"role": "system", "content": f"{COMPACTION_SUMMARY_MARKER} folded notes"},
    ]
    evt = compaction_event(
        before, after, {"prompt_tokens": 3, "completion_tokens": 4, "latency_ms": 5.0},
        context_window=8000, threshold=0.5,
    )
    assert evt is not None
    assert evt["type"] == "compaction"
    assert evt["summarized"] is True
    assert evt["context_window"] == 8000
    assert evt["threshold"] == 0.5
    # Non-dict rows and non-summary systems stay quiet.
    assert compaction_event(["bad"], ["bad"]) is None  # type: ignore[list-item]
    assert compaction_event(before, before) is None

def test_summary_markers_tolerates_shapes() -> None:
    from realmock.domains.prep.agents.persist import _summary_markers
    from realmock.platform.capabilities.ai.context.compress import COMPACTION_SUMMARY_MARKER

    assert _summary_markers([]) == set()
    assert _summary_markers(["bad", {"role": "user", "content": "x"}]) == set()
    assert _summary_markers([{"role": "system", "content": f"{COMPACTION_SUMMARY_MARKER} a"}]) != set()

@pytest.mark.asyncio
async def test_persist_cancel_never_raises(monkeypatch) -> None:
    import realmock.domains.prep.agents.persist as persist_mod
    from realmock.domains.prep.agents.agent import PrepAgent

    sess = SimpleNamespace(messages="[]", resume_id=None, target_company="",
                           target_role="", token_usage=0, prompt_tokens=0,
                           completion_tokens=0, cached_tokens=0)
    agent = PrepAgent(sess, SimpleNamespace(context_window=8000))  # type: ignore[arg-type]

    def _boom(*args, **kwargs):
        raise RuntimeError("persist-down")

    monkeypatch.setattr(persist_mod, "finalize", _boom)
    # Must not raise even when finalize fails.
    persist_mod.persist_cancel(agent, [], "", {"filtered_text": "x"}, object())  # type: ignore[arg-type]


def test_finalize_persists_last_round_usage(monkeypatch) -> None:
    """finalize writes the turn's last LLM call usage into the session columns."""
    from realmock.domains.prep.agents import persist as persist_mod
    from realmock.domains.prep.agents.agent import PrepAgent

    sess = SimpleNamespace(messages="[]", resume_id=None, target_company="",
                           target_role="", token_usage=0, prompt_tokens=0,
                           completion_tokens=0, cached_tokens=0,
                           last_round_prompt_tokens=0, last_round_completion_tokens=0,
                           status="active", access_token="", linked_session_id=None,
                           summary="", message_count=0)
    saved: list[SimpleNamespace] = []

    class _Agent(PrepAgent):
        def _save(self, db):
            saved.append(self.session)

    agent = _Agent(sess, SimpleNamespace(context_window=8000))  # type: ignore[arg-type]
    agent.messages = [{"role": "user", "content": "hi"}]
    agent.last_round_usage = {"prompt_tokens": 150, "completion_tokens": 10, "cached_tokens": 120}

    monkeypatch.setattr(persist_mod, "prepare_llm_context", lambda messages, *a, **k: messages)
    persist_mod.finalize(agent, [{"role": "user", "content": "hi"}], "answer", object())  # type: ignore[arg-type]

    assert saved, "finalize must persist"
    assert sess.last_round_prompt_tokens == 150
    assert sess.last_round_completion_tokens == 10
    # Without a recorded last round, the columns stay untouched (0).
    sess2 = SimpleNamespace(**{**vars(sess), "last_round_prompt_tokens": 0,
                               "last_round_completion_tokens": 0})
    agent2 = _Agent(sess2, SimpleNamespace(context_window=8000))  # type: ignore[arg-type]
    agent2.messages = [{"role": "user", "content": "hi"}]
    agent2.last_round_usage = None
    persist_mod.finalize(agent2, [{"role": "user", "content": "hi"}], "answer", object())  # type: ignore[arg-type]
    assert sess2.last_round_prompt_tokens == 0
    assert sess2.last_round_completion_tokens == 0
