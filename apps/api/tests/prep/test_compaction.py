"""Compaction parameters, agent-invoked compaction, backup/rollback, and overflow classification."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.domains.prep.agents.agent import PrepAgent
from realmock.domains.prep.agents.chat import finalize
from realmock.domains.prep.models import PrepSession
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.capabilities.ai.llm.provider_errors import is_context_overflow
from realmock.platform.core.session_auth import new_access_token


class _UsageStub:
    """Minimal usage accumulator double (to_dict only, like the real one)."""

    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_tokens = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cached_tokens": self.cached_tokens,
        }


class _SummaryLLM:
    """Fake summarizer: every chat call appends fixed usage and returns one summary."""

    context_window = 128000

    def __init__(self, reply: str = "Session objectives: ship it") -> None:
        self.reply = reply
        self.chat_calls: list[list[dict]] = []
        self.kwargs: list[dict] = []
        self.usage = _UsageStub()

    async def chat(self, messages, temperature=0.7, max_tokens=None, system=None, purpose=None, **kwargs):
        del temperature, max_tokens, kwargs
        self.chat_calls.append(messages)
        self.kwargs.append({"system": system, "purpose": purpose})
        self.usage.prompt_tokens += 100
        self.usage.completion_tokens += 20
        return self.reply


def _session_with_messages(db, messages: list[dict], status: str = "active") -> PrepSession:
    session = PrepSession(
        access_token=new_access_token(),
        status=status,
        messages=json.dumps(messages, ensure_ascii=False),
        target_role="Backend",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _big_turns(n: int = 4) -> list[dict]:
    msgs: list[dict] = []
    for i in range(n):
        msgs.append({"role": "user", "content": f"Question{i} " + "Body" * 120})
        msgs.append({"role": "assistant", "content": f"Answer{i} " + "Detail" * 120})
    return msgs


def _compact(client: TestClient, session_id: int, body: dict | None = None):
    if body is None:
        return client.post(
            f"/api/v1/prep/sessions/{session_id}/compact",
            headers={"Origin": "http://localhost:8080"},
        )
    return client.post(
        f"/api/v1/prep/sessions/{session_id}/compact",
        headers={"Origin": "http://localhost:8080"},
        json=body,
    )


# ── Manual /compact with parameters ──────────────────────────────────────────


def test_compact_with_params_summarizes_and_reports(db, monkeypatch) -> None:
    fake = _SummaryLLM()
    monkeypatch.setattr(LLMClient, "from_db", classmethod(lambda cls, *a, **k: fake))
    # System seed first (real sessions always carry one; the summarizer replays it).
    session = _session_with_messages(db, [{"role": "system", "content": "Coach instructions"}] + _big_turns())
    with TestClient(app) as client:
        resp = _compact(client, session.id, {
            "intensity": "aggressive",
            "directive": "prioritize errors",
            "retain": 2,
        })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summarized"] is True
    assert body["reason"] == "summarized"
    assert "ship it" in body["summary_text"]
    assert "[provenance" not in body["summary_text"]
    assert body["summary_version"] == 1
    assert body["fork_point"] == 9
    assert body["kept_from"] == 7
    assert body["estimate_after"] < body["estimate_before"]
    assert body["compaction_prompt_tokens"] == 100
    assert body["compaction_completion_tokens"] == 20
    assert body["compaction_latency_ms"] >= 0
    # Rolling backup fork preserves the pre-compaction originals, archived.
    assert body["backup_session_id"] is not None
    db.expire_all()
    backup = db.get(PrepSession, body["backup_session_id"])
    assert backup is not None and backup.status == "archived"
    assert len(json.loads(backup.messages)) == 9
    # The summarizer saw the stable system prefix, the directive, and the purpose tag.
    assert fake.kwargs and fake.kwargs[0]["purpose"] == "compaction"
    assert fake.kwargs[0]["system"]
    assert "prioritize errors" in fake.chat_calls[0][0]["content"]


def test_compact_rolls_backup_and_bumps_version(db, monkeypatch) -> None:
    fake = _SummaryLLM()
    monkeypatch.setattr(LLMClient, "from_db", classmethod(lambda cls, *a, **k: fake))
    session = _session_with_messages(db, _big_turns())
    with TestClient(app) as client:
        first = _compact(client, session.id, {"retain": 2}).json()
        # Grow history again so the second run has something to fold.
        db.expire_all()
        stored = json.loads(db.get(PrepSession, session.id).messages)
        stored += _big_turns()
        row = db.get(PrepSession, session.id)
        row.messages = json.dumps(stored, ensure_ascii=False)
        db.commit()
        second = _compact(client, session.id, {"retain": 2}).json()
    assert second["summary_version"] == 2
    assert second["summarized"] is True
    db.expire_all()
    assert db.get(PrepSession, first["backup_session_id"]) is None, "rolling backup replaces the previous one"
    assert db.get(PrepSession, second["backup_session_id"]) is not None


def test_compact_conflicts_on_stale_expected_count(db, monkeypatch) -> None:
    fake = _SummaryLLM()
    monkeypatch.setattr(LLMClient, "from_db", classmethod(lambda cls, *a, **k: fake))
    session = _session_with_messages(db, _big_turns())
    with TestClient(app) as client:
        resp = _compact(client, session.id, {"expected_message_count": 999})
    assert resp.status_code == 409, resp.text
    assert fake.chat_calls == [], "conflict must short-circuit before any LLM call"


def test_compact_rejects_invalid_params(db) -> None:
    session = _session_with_messages(db, _big_turns())
    with TestClient(app) as client:
        assert _compact(client, session.id, {"retain": -1}).status_code == 422
        assert _compact(client, session.id, {"retain": 201}).status_code == 422
        assert _compact(client, session.id, {"intensity": "turbo"}).status_code == 422
        assert _compact(client, session.id, {"directive": "x" * 501}).status_code == 422


# ── Summary edit ─────────────────────────────────────────────────────────────


def test_summary_edit_and_missing_summary(db, monkeypatch) -> None:
    fake = _SummaryLLM()
    monkeypatch.setattr(LLMClient, "from_db", classmethod(lambda cls, *a, **k: fake))
    bare = _session_with_messages(db, _big_turns())
    session = _session_with_messages(db, _big_turns())
    with TestClient(app) as client:
        missing = client.patch(
            f"/api/v1/prep/sessions/{bare.id}/summary",
            headers={"Origin": "http://localhost:8080"},
            json={"text": "edited"},
        )
        assert missing.status_code == 404, missing.text
        compacted = _compact(client, session.id, {"retain": 2}).json()
        edited = client.patch(
            f"/api/v1/prep/sessions/{session.id}/summary",
            headers={"Origin": "http://localhost:8080"},
            json={"text": "Corrected notes", "expected_message_count": compacted["message_count"]},
        )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["reason"] == "edited"
    assert body["summary_text"] == "Corrected notes"
    assert body["summary_version"] == 2
    # Backup/fork linkage carries over the edit.
    assert body["backup_session_id"] == compacted["backup_session_id"]
    assert body["fork_point"] == compacted["fork_point"]
    db.expire_all()
    stored = json.loads(db.get(PrepSession, session.id).messages)
    assert sum(1 for m in stored if str(m.get("content") or "").startswith("[Conversation Minutes]")) == 1


# ── Agent-invoked compact tool ───────────────────────────────────────────────


class _FakeSession:
    messages = "[]"
    resume_id = None
    target_company = ""
    token_usage = 0
    prompt_tokens = 0
    completion_tokens = 0
    cached_tokens = 0


class _FakeDB:
    def commit(self) -> None:
        pass


def _agent_with_history(n_turns: int, **llm_kwargs) -> PrepAgent:
    session = _FakeSession()
    session.messages = json.dumps(_big_turns(n_turns), ensure_ascii=False)
    llm = _SummaryLLM(**llm_kwargs)
    return PrepAgent(session, llm)  # type: ignore[arg-type]


def test_agent_compact_tool_refuses_small_session() -> None:
    import asyncio

    agent = _agent_with_history(1)
    text, _ = asyncio.run(agent._compact_current_round({}, _FakeDB()))  # type: ignore[arg-type]
    assert "not needed" in text


def test_agent_compact_tool_runs_once_and_folds() -> None:
    import asyncio

    agent = _agent_with_history(6)
    # Force over the absolute floor regardless of the fake window.
    agent.context_window = 1000
    first, _ = asyncio.run(agent._compact_current_round({}, _FakeDB()))  # type: ignore[arg-type]
    assert "compacted by summarizer" in first
    stored = json.loads(agent.session.messages)
    assert any(str(m.get("content") or "").startswith("[Conversation Minutes]") for m in stored)
    assert agent._turn_state.mid_turn_report is not None
    second, _ = asyncio.run(agent._compact_current_round({}, _FakeDB()))  # type: ignore[arg-type]
    assert "already ran" in second


def test_agent_compact_tool_honors_focus_and_intensity() -> None:
    """Per-call focus/intensity override the turn policy for that run only."""
    import asyncio

    agent = _agent_with_history(6)
    agent.context_window = 1000
    assert agent._turn_state.policy.intensity == "balanced"
    text, _ = asyncio.run(agent._compact_current_round(
        {"reason": "long exploration", "focus": "prioritize errors", "intensity": "aggressive"},
        _FakeDB(),
    ))  # type: ignore[arg-type]
    assert "aggressive" in text and "prioritize errors" in text
    # The focus reached the summarizer prompt, not just the observation.
    assert any(
        "prioritize errors" in str(m.get("content") or "")
        for call in agent.llm.chat_calls
        for m in call
    )
    # The turn policy itself is untouched (override is per-run).
    assert agent._turn_state.policy.intensity == "balanced"
    assert agent._turn_state.policy.directive == ""


def test_agent_compact_tool_ignores_invalid_intensity() -> None:
    import asyncio

    agent = _agent_with_history(6)
    agent.context_window = 1000
    text, _ = asyncio.run(agent._compact_current_round(
        {"intensity": "turbo", "focus": 123},
        _FakeDB(),
    ))  # type: ignore[arg-type]
    assert "compacted by summarizer (balanced)" in text


def test_finalize_merges_loop_tail_onto_mid_turn_base() -> None:
    import asyncio

    agent = _agent_with_history(6)
    agent.context_window = 1000
    asyncio.run(agent._compact_current_round({}, _FakeDB()))  # type: ignore[arg-type]
    # Simulate the in-flight loop: working copy kept growing after the compaction.
    working = list(agent.messages)
    agent._turn_state.pre_loop_len = len(working)
    working.append({"role": "assistant", "content": None,
                    "tool_calls": [{"id": "c9", "type": "function",
                                    "function": {"name": "web_search", "arguments": "{}"}}]})
    working.append({"role": "tool", "tool_call_id": "c9", "content": "fresh observation"})
    finalize(agent, working, "final answer", _FakeDB(), turn_id="t1")  # type: ignore[arg-type]
    contents = [m.get("content") for m in agent.messages]
    assert contents.count("final answer") == 1
    assert any(m.get("tool_call_id") == "c9" for m in agent.messages), "current-round tool pair must survive"
    # The persisted tail ends with the working-memory block (pre-existing
    # finalize shape); the assistant reply carries the turn id.
    assistants = [m for m in agent.messages if m.get("role") == "assistant"]
    assert assistants and assistants[-1].get("turn_id") == "t1"
    assert agent._turn_state.mid_turn_base is None, "merge consumes the base"


def test_finalize_records_backend_truth_count() -> None:
    """finalize exposes the persisted length so clients resync instead of guessing."""
    agent = _agent_with_history(2)
    working = list(agent.messages)
    agent._turn_state.pre_loop_len = len(working)
    finalize(agent, working, "final answer", _FakeDB(), turn_id="t9")  # type: ignore[arg-type]
    assert agent.last_message_count == len(agent.messages) > 0


def test_finalize_after_drop_keeps_single_assistant() -> None:
    """Regenerate-style drop followed by a stopped persist must not duplicate the reply."""
    from realmock.domains.prep.agents.chat import _drop_trailing_assistant

    agent = _agent_with_history(1)
    _drop_trailing_assistant(agent)
    assert agent.messages[-1].get("role") == "user"
    finalize(agent, list(agent.messages), "partial", _FakeDB(), stopped=True, turn_id="t2")  # type: ignore[arg-type]
    assistants = [m for m in agent.messages if m.get("role") == "assistant"]
    assert len(assistants) == 1 and assistants[0].get("stopped") is True


# ── Overflow classification ──────────────────────────────────────────────────


class _HttpError(Exception):
    def __init__(self, status: int, text: str) -> None:
        super().__init__(f"HTTP {status}")
        self.response = type("R", (), {"status_code": status, "text": text})()


def test_is_context_overflow() -> None:
    assert is_context_overflow(_HttpError(400, '{"code":"context_length_exceeded"}'))
    assert is_context_overflow(_HttpError(400, "This model's maximum context length is 128000 tokens"))
    assert is_context_overflow(Exception("context_window_exceeded"))
    assert not is_context_overflow(_HttpError(429, "rate limit, retry later"))
    assert not is_context_overflow(_HttpError(401, "invalid api key"))
    assert not is_context_overflow(_HttpError(500, "maximum context length" * 0 + "internal error"))
    assert not is_context_overflow(Exception("boom"))
    assert is_context_overflow(None) is False  # type: ignore[arg-type]
