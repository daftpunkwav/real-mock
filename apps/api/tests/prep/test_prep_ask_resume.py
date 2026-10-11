"""Paused-dialog resume: the ask_user turn pauses on an open tool_call and the
next user input (popup answer or free-typed text — same channel) completes it
and re-enters the SAME turn, so the original task stays the live task."""

from __future__ import annotations

import asyncio
import json

from realmock.domains.prep.agents.agent import PrepAgent


class _CapturingLLM:
    """Scripted replies that record the model input of every call."""

    def __init__(self, replies: list[dict]):
        self.replies = list(replies)
        self.calls = 0
        self.seen_inputs: list[list[dict]] = []

    async def chat_message(self, messages, temperature=0.7, tools=None, **kwargs):
        """Record the model input, then return the next scripted reply."""
        del temperature, tools, kwargs
        self.seen_inputs.append([dict(m) for m in messages])
        idx = min(self.calls, len(self.replies) - 1)
        self.calls += 1
        return self.replies[idx]


class _FakeSession:
    """Minimal PrepSession stand-in whose messages column persists in memory."""

    messages = "[]"
    resume_id = None
    target_company = ""
    token_usage = 0
    prompt_tokens = 0
    completion_tokens = 0
    cached_tokens = 0


class _FakeDB:
    """No-op DB session: commits land nowhere, queries resolve to nothing."""

    def commit(self):
        pass

    def rollback(self):
        pass

    def query(self, model):
        return self

    def first(self):
        return None


def _ask_call(question: str, options: list[str], call_id: str = "c1") -> dict:
    """One assistant round whose only tool_call opens an ask_user dialog."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "function": {
                    "name": "ask_user",
                    "arguments": json.dumps(
                        {"question": question, "options": options}, ensure_ascii=False
                    ),
                },
            }
        ],
    }


def _stored(session: _FakeSession) -> list[dict]:
    """The session's persisted history as a message list."""
    return json.loads(session.messages)


def _last_user_row(model_input: list[dict]) -> dict:
    """The latest user row of a captured model input (hints trail after it)."""
    return next(m for m in reversed(model_input) if m.get("role") == "user")


def test_paused_dialog_resumes_on_next_input() -> None:
    """Turn 1 pauses on an open dialog; turn 2's answer completes the call and
    the same turn continues — the model sees its own question answered."""
    session = _FakeSession()
    db = _FakeDB()
    # Turn 1: the model opens a dialog mid-task; the turn pauses on the open call.
    agent1 = PrepAgent(session, _CapturingLLM([_ask_call("Which direction?", ["A", "B"])]))  # type: ignore[arg-type]

    async def run_turn1():
        return [
            item async for item in agent1.chat_stream("Test these tools: ask_user, take_note", db)
        ]  # type: ignore[arg-type]

    items1 = asyncio.run(run_turn1())
    assert any(isinstance(i, dict) and i.get("type") == "ask_user" for i in items1)
    stored = _stored(session)
    pending = [m for m in stored if m.get("ask_pending")]
    assert len(pending) == 1, "the open call is marked for resume"
    assert pending[0]["keep_tool_pair"] is True
    assert not [m for m in stored if m.get("role") == "tool"], "no result yet for the open call"

    # Turn 2: the user's popup answer arrives through the same message channel.
    llm2 = _CapturingLLM(
        [{"role": "assistant", "content": "Continuing the tool test.", "tool_calls": None}]
    )  # type: ignore[arg-type]
    agent2 = PrepAgent(session, llm2)  # type: ignore[arg-type]

    async def run_turn2():
        return [item async for item in agent2.chat_stream("A", db)]  # type: ignore[arg-type]

    items2 = asyncio.run(run_turn2())
    assert any(isinstance(i, str) and "Continuing the tool test" in i for i in items2)

    # The model saw the pointer observation completing its own call, with the
    # answer as the latest user message — same turn, task still live.
    model_input = llm2.seen_inputs[0]
    assert any(
        m.get("role") == "user" and "Test these tools" in str(m.get("content")) for m in model_input
    ), "the original task is still in the resumed model input"
    pointer = [m for m in model_input if m.get("role") == "tool"]
    assert len(pointer) == 1 and "[ask_user]" in pointer[0]["content"]
    open_call_id = pending[0]["tool_calls"][0]["id"]
    assert pointer[0]["tool_call_id"] == open_call_id
    assert _last_user_row(model_input) == {"role": "user", "content": "A"}

    stored = _stored(session)
    assert not [m for m in stored if m.get("ask_pending")], "exchange closed on resume"
    # Once answered, the protection flag drops (finalize sweeps it) and the
    # exchange folds like any old tool round; the answer itself survives as a
    # real user row (display/retract semantics unchanged).
    assert not [m for m in stored if m.get("role") == "tool"]
    assert not [m for m in stored if m.get("keep_tool_pair")]
    assert any(m.get("role") == "user" and m.get("content") == "A" for m in stored)
    final_rows = [m for m in stored if m.get("role") == "assistant"]
    assert "Continuing the tool test" in final_rows[-1]["content"]


def test_free_typed_text_answers_the_dialog_too() -> None:
    """A typed message (not the popup) resolves the pending dialog the same way."""
    session = _FakeSession()
    db = _FakeDB()
    agent1 = PrepAgent(session, _CapturingLLM([_ask_call("Next step?", ["Quiz", "Drill"])]))  # type: ignore[arg-type]
    asyncio.run(
        _drain(agent1.chat_stream("Test these tools", db))  # type: ignore[arg-type]
    )

    llm2 = _CapturingLLM([{"role": "assistant", "content": "ok", "tool_calls": None}])  # type: ignore[arg-type]
    agent2 = PrepAgent(session, llm2)  # type: ignore[arg-type]
    asyncio.run(_drain(agent2.chat_stream("let us do the quiz", db)))  # type: ignore[arg-type]

    model_input = llm2.seen_inputs[0]
    assert _last_user_row(model_input) == {"role": "user", "content": "let us do the quiz"}
    assert any(
        m.get("role") == "user" and "Test these tools" in str(m.get("content")) for m in model_input
    ), "the original task is still in the resumed model input"
    assert any(
        m.get("role") == "tool" and "[ask_user]" in str(m.get("content")) for m in model_input
    )
    assert not [m for m in _stored(session) if m.get("ask_pending")]


def test_regenerate_discards_paused_dialog() -> None:
    """Regenerating the asking turn replays the task fresh: the open dialog is
    discarded whole (declaration + waiting-line row), no phantom resume."""
    session = _FakeSession()
    db = _FakeDB()
    task = "Test these tools"
    agent1 = PrepAgent(session, _CapturingLLM([_ask_call("Which?", ["A", "B"])]))  # type: ignore[arg-type]
    asyncio.run(_drain(agent1.chat_stream(task, db)))  # type: ignore[arg-type]
    assert [m for m in _stored(session) if m.get("ask_pending")]

    llm2 = _CapturingLLM([{"role": "assistant", "content": "fresh answer", "tool_calls": None}])  # type: ignore[arg-type]
    agent2 = PrepAgent(session, llm2)  # type: ignore[arg-type]
    asyncio.run(_drain(agent2.chat_stream(task, db, drop_last_assistant=True)))  # type: ignore[arg-type]

    stored = _stored(session)
    assert not [m for m in stored if m.get("ask_pending")]
    assert not [m for m in stored if m.get("role") == "tool"]
    assert not any(
        m.get("tool_calls")
        and any(tc.get("function", {}).get("name") == "ask_user" for tc in m["tool_calls"])
        for m in stored
    ), "no ask_user declaration survives nested in tool_calls"
    assert not any("ask" in m for m in stored), "paused structure discarded whole"
    # The replayed task runs as a normal turn: user row + final answer.
    assert [m for m in stored if m.get("role") == "user"] == [{"role": "user", "content": task}]
    final_rows = [m for m in stored if m.get("role") == "assistant"]
    assert final_rows[-1]["content"] == "fresh answer"


def test_resume_with_sibling_tool_result_keeps_pairing() -> None:
    """A parallel sibling call in the pause round stores its result before the
    waiting line; the resume pointer lands between the declaration and the
    sibling result, and both calls stay protocol-paired by id."""
    session = _FakeSession()
    db = _FakeDB()
    ask_llm = _CapturingLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "function": {
                            "name": "ask_user",
                            "arguments": json.dumps({"question": "Which?", "options": ["A", "B"]}),
                        },
                    },
                    {"id": "sib", "function": {"name": "take_note", "arguments": "{}"}},
                ],
            }
        ]
    )
    agent1 = PrepAgent(session, ask_llm)  # type: ignore[arg-type]
    asyncio.run(_drain(agent1.chat_stream("Test these tools", db)))  # type: ignore[arg-type]

    stored = _stored(session)
    assert any(m.get("ask_pending") for m in stored), "the open call is marked"
    # The sibling result persisted; the open call did not get one.
    assert [m["tool_call_id"] for m in stored if m.get("role") == "tool"] == ["sib"]

    llm2 = _CapturingLLM([{"role": "assistant", "content": "resumed", "tool_calls": None}])  # type: ignore[arg-type]
    agent2 = PrepAgent(session, llm2)  # type: ignore[arg-type]
    asyncio.run(_drain(agent2.chat_stream("A", db)))  # type: ignore[arg-type]

    model_input = llm2.seen_inputs[0]
    declaration = next(
        m for m in model_input if m.get("tool_calls") and m.get("role") == "assistant"
    )
    declared_ids = [tc.get("id") for tc in declaration["tool_calls"]]
    assert declared_ids == ["c1", "sib"], "the declaration keeps both calls"
    pointer_index = next(
        i
        for i, m in enumerate(model_input)
        if m.get("role") == "tool" and "[ask_user]" in str(m.get("content"))
    )
    declaration_index = model_input.index(declaration)
    assert pointer_index == declaration_index + 1, "pointer directly follows the declaration"
    assert any(m.get("role") == "tool" and m.get("tool_call_id") == "sib" for m in model_input), (
        "sibling result still paired with its declared call"
    )


def test_regenerate_tool_turn_drops_whole_exchange() -> None:
    """Regenerating a normal tool turn pops the declarations together with
    their results — stopping at a declaration would leave it unpaired and
    duplicate the question row."""
    session = _FakeSession()
    db = _FakeDB()
    task = "run the numbers"
    llm1 = _CapturingLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "t1", "function": {"name": "take_note", "arguments": "{}"}}],
            },
            {"role": "assistant", "content": "answer with tools", "tool_calls": None},
        ]
    )
    agent1 = PrepAgent(session, llm1)  # type: ignore[arg-type]
    asyncio.run(_drain(agent1.chat_stream(task, db)))  # type: ignore[arg-type]
    assert [m for m in _stored(session) if m.get("role") == "tool"], "tool turn stored"

    llm2 = _CapturingLLM([{"role": "assistant", "content": "fresh", "tool_calls": None}])  # type: ignore[arg-type]
    agent2 = PrepAgent(session, llm2)  # type: ignore[arg-type]
    asyncio.run(_drain(agent2.chat_stream(task, db, drop_last_assistant=True)))  # type: ignore[arg-type]

    stored = _stored(session)
    assert not [m for m in stored if m.get("role") == "tool"], "results popped with owner"
    assert not [m for m in stored if m.get("tool_calls")], "no unpaired declaration stays"
    assert [m.get("content") for m in stored if m.get("role") == "user"] == [task]


async def _drain(agen):
    """Collect an async iterator into a list."""
    return [item async for item in agen]
