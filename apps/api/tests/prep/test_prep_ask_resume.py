"""Paused-dialog resume: the ask_user turn pauses on an open tool_call and the
next user input (popup answer or free-typed text — same channel) completes it
and re-enters the SAME turn, so the original task stays the live task."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from realmock.domains.prep.agents.agent import PrepAgent
from realmock.domains.prep.agents.chat import _persist_failure_state
from realmock.domains.prep.agents.tools.repo.github import GITHUB_TOOL_NAMES
from realmock.platform.core.errors import CATALOG, ApiBusinessError


class _CapturingLLM:
    """Scripted replies that record the model input of every call."""

    def __init__(self, replies: list[dict]):
        self.replies = list(replies)
        self.calls = 0
        self.seen_inputs: list[list[dict]] = []
        self.seen_tool_names: list[list[str]] = []

    async def chat_message(self, messages, temperature=0.7, tools=None, **kwargs):
        """Record the model input, then return the next scripted reply."""
        del temperature, kwargs
        self.seen_inputs.append([dict(m) for m in messages])
        self.seen_tool_names.append(
            [str((t.get("function") or {}).get("name") or "") for t in (tools or [])]
        )
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


def test_dialog_reaches_the_client_only_after_the_pause_state_is_persisted() -> None:
    """The dialog event is emitted after the pause state is committed.

    The user must never hold a dialog whose resume state history cannot serve:
    a turn lost between the emit and the save leaves their answer starting a
    new task instead of resuming the interrupted one. Asserting on the stored
    history at the moment the event is yielded is the only place the ordering
    is observable.
    """
    session = _FakeSession()
    db = _FakeDB()
    agent = PrepAgent(session, _CapturingLLM([_ask_call("Which?", ["A", "B"])]))  # type: ignore[arg-type]

    async def stored_at_dialog() -> list[dict]:
        agen = agent.chat_stream("Test these tools", db)  # type: ignore[arg-type]
        async for item in agen:
            if isinstance(item, dict) and item.get("type") == "ask_user":
                return _stored(session)
        return []

    stored = asyncio.run(stored_at_dialog())
    assert [m for m in stored if m.get("ask_pending")], (
        "the open call was still unpersisted when the dialog reached the client"
    )
    assert not [m for m in stored if m.get("role") == "tool"], "the dialog call has no result yet"


def test_cancel_during_pause_persists_the_resume_marker() -> None:
    """Stopping the stream after the dialog event still lands the pause state.

    The loop runs on its own copy of the working list, so the cancel path must
    persist that copy: the open call's declaration exists only there, and
    landing the loop-entry list would save the dialog without ``ask_pending``
    — the user's next answer would start a new task."""
    session = _FakeSession()
    db = _FakeDB()
    agent1 = PrepAgent(session, _CapturingLLM([_ask_call("Which?", ["A", "B"])]))  # type: ignore[arg-type]

    async def run_and_stop():
        agen = agent1.chat_stream("Test these tools", db)  # type: ignore[arg-type]
        async for item in agen:
            if isinstance(item, dict) and item.get("type") == "ask_user":
                break
        await agen.aclose()

    asyncio.run(run_and_stop())

    stored = _stored(session)
    pending = [m for m in stored if m.get("ask_pending")]
    assert len(pending) == 1, "the cancel persist marked the open call from the loop copy"
    assert pending[0]["keep_tool_pair"] is True
    assert not [m for m in stored if m.get("role") == "tool"], "no result for the open call"

    llm2 = _CapturingLLM([{"role": "assistant", "content": "resumed", "tool_calls": None}])  # type: ignore[arg-type]
    agent2 = PrepAgent(session, llm2)  # type: ignore[arg-type]
    asyncio.run(_drain(agent2.chat_stream("A", db)))  # type: ignore[arg-type]
    assert any(
        m.get("role") == "tool" and "[ask_user]" in str(m.get("content"))
        for m in llm2.seen_inputs[0]
    ), "the next input resumes the paused dialog"


def test_failed_prepare_keeps_the_dialog_resumable() -> None:
    """A context-build failure after the answer was appended must not consume
    the dialog: the failed-turn persist keeps ``ask_pending`` (no pointer row),
    so the retry resumes the same dialog instead of starting a new task."""
    session = _FakeSession()
    db = _FakeDB()
    agent1 = PrepAgent(session, _CapturingLLM([_ask_call("Which?", ["A", "B"])]))  # type: ignore[arg-type]
    asyncio.run(_drain(agent1.chat_stream("Test these tools", db)))  # type: ignore[arg-type]
    assert [m for m in _stored(session) if m.get("ask_pending")]

    agent2 = PrepAgent(session, _CapturingLLM([{"role": "assistant", "content": "ok"}]))  # type: ignore[arg-type]

    async def _boom(*args, **kwargs):
        raise RuntimeError("context-build-down")

    agent2._build_context = _boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="context-build-down"):
        asyncio.run(_drain(agent2.chat_stream("A", db)))  # type: ignore[arg-type]

    stored = _stored(session)
    assert [m for m in stored if m.get("ask_pending")], "the marker was restored for the retry"
    assert not [m for m in stored if m.get("role") == "tool"], "no pointer result landed"
    assert not any(m.get("role") == "user" and m.get("content") == "A" for m in stored), (
        "the just-typed answer is dropped with the failed turn (a retry would duplicate it)"
    )

    llm3 = _CapturingLLM([{"role": "assistant", "content": "resumed", "tool_calls": None}])  # type: ignore[arg-type]
    agent3 = PrepAgent(session, llm3)  # type: ignore[arg-type]
    asyncio.run(_drain(agent3.chat_stream("A", db)))  # type: ignore[arg-type]
    assert any(
        m.get("role") == "tool" and "[ask_user]" in str(m.get("content"))
        for m in llm3.seen_inputs[0]
    ), "the retry after the failed prepare resumes the dialog"


def test_failed_resume_turn_rolls_back_to_paused_snapshot() -> None:
    """A resume turn that dies mid-loop (business error from a domain tool)
    persists the exact paused snapshot: the pointer, the answer row, and the
    consumed marker are all rolled back, so a retry resumes cleanly."""
    session = _FakeSession()
    db = _FakeDB()
    agent1 = PrepAgent(session, _CapturingLLM([_ask_call("Which?", ["A", "B"])]))  # type: ignore[arg-type]
    asyncio.run(_drain(agent1.chat_stream("Test these tools", db)))  # type: ignore[arg-type]
    snapshot = _stored(session)
    assert [m for m in snapshot if m.get("ask_pending")]

    agent2 = PrepAgent(
        session,
        _CapturingLLM(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": "t1", "function": {"name": "take_note", "arguments": "{}"}}
                    ],
                }
            ]
        ),  # type: ignore[arg-type]
    )

    async def _boom(name, args, db):
        raise ApiBusinessError(CATALOG["A3001"], message="quota gone")

    agent2._run_named_tool = _boom  # type: ignore[method-assign]

    with pytest.raises(ApiBusinessError):
        asyncio.run(_drain(agent2.chat_stream("A", db)))  # type: ignore[arg-type]

    assert _stored(session) == snapshot, "the failed resume rolled back to the pause snapshot"


def test_persist_failure_state_lands_pause_from_loop_copy(monkeypatch) -> None:
    """A turn failure after the dialog fired lands the pause state from the
    loop's working copy (defense for the dialog-shown window; the engine's
    sibling gate makes the parallel-error race itself unreachable today)."""
    import realmock.domains.prep.agents.chat as chat_mod

    agent = SimpleNamespace(
        pending_reply_text=lambda: "waiting-line",
        messages=[{"role": "user", "content": "task"}],
        session=SimpleNamespace(id=1),
    )
    captured: dict = {}

    def _fake_cancel(agent_, working, final, content_state, db, **kwargs):
        captured["working"] = working
        captured["final"] = final
        captured.update(kwargs)

    monkeypatch.setattr(chat_mod, "persist_cancel", _fake_cancel)

    dialog = {"question": "Q?", "options": ["A", "B"]}
    handled = _persist_failure_state(
        agent,  # type: ignore[arg-type]
        {"on": True, "event": dialog},
        {"working": [{"role": "assistant", "tool_calls": []}]},
        [{"role": "user", "content": "task"}],
        "turn-1",
        None,
        _FakeDB(),  # type: ignore[arg-type]
    )
    assert handled is True
    assert captured["working"] == [{"role": "assistant", "tool_calls": []}], (
        "the loop's working copy is landed, not the loop-entry list"
    )
    assert captured["pause_event"] == dialog and captured["ask"] == dialog
    assert captured["final"] == "waiting-line"

    handled_off = _persist_failure_state(
        agent,  # type: ignore[arg-type]
        {"on": False},
        {},
        [],
        "turn-1",
        None,
        _FakeDB(),  # type: ignore[arg-type]
    )
    assert handled_off is False, "no fired dialog falls through to the plain failed-turn path"


def test_second_resume_freezes_toolset_from_original_task() -> None:
    """A task that opens a second dialog keeps its text-gated tools across
    BOTH resumes: the first answer carries no repo signal, so freezing from
    it would drop the github tools the task still needs."""
    session = _FakeSession()
    db = _FakeDB()
    llm1 = _CapturingLLM([_ask_call("Which repo part?", ["Perf", "API"])])  # type: ignore[arg-type]
    agent1 = PrepAgent(session, llm1)  # type: ignore[arg-type]
    asyncio.run(_drain(agent1.chat_stream("Review github.com/owner/repo for me", db)))  # type: ignore[arg-type]

    llm2 = _CapturingLLM([_ask_call("And which depth?", ["Quick", "Deep"])])  # type: ignore[arg-type]
    agent2 = PrepAgent(session, llm2)  # type: ignore[arg-type]
    asyncio.run(_drain(agent2.chat_stream("Perf", db)))  # type: ignore[arg-type]

    llm3 = _CapturingLLM([{"role": "assistant", "content": "done", "tool_calls": None}])  # type: ignore[arg-type]
    agent3 = PrepAgent(session, llm3)  # type: ignore[arg-type]
    asyncio.run(_drain(agent3.chat_stream("Deep", db)))  # type: ignore[arg-type]

    assert any(name in llm3.seen_tool_names[0] for name in GITHUB_TOOL_NAMES), (
        "the second resume still freezes the toolset from the original task text"
    )


def test_corrupt_pending_marker_degrades_to_normal_turn() -> None:
    """A stored ``ask_pending`` row whose open call cannot be resolved no
    longer strands a dangling declaration: the marker is dropped, the
    declaration gets a synthesized result, and the input runs as a normal
    turn instead of a guaranteed provider rejection."""
    session = _FakeSession()
    session.messages = json.dumps(
        [
            {"role": "user", "content": "earlier task"},
            {
                "role": "assistant",
                "content": None,
                "ask_pending": True,
                "keep_tool_pair": True,
                "tool_calls": [{"function": {"name": "ask_user", "arguments": "{}"}}],
            },
        ]
    )
    db = _FakeDB()
    llm = _CapturingLLM([{"role": "assistant", "content": "fresh turn", "tool_calls": None}])  # type: ignore[arg-type]
    agent = PrepAgent(session, llm)  # type: ignore[arg-type]
    asyncio.run(_drain(agent.chat_stream("A", db)))  # type: ignore[arg-type]

    stored = _stored(session)
    assert not [m for m in stored if m.get("ask_pending")], "the corrupt marker was dropped"
    # The model request must be protocol-clean: every declared call carries a
    # result (the unresolvable declaration got a synthesized one; finalize may
    # legitimately fold the completed pair away afterwards).
    model_input = llm.seen_inputs[0]
    declared = {
        tc.get("id")
        for m in model_input
        if isinstance(m.get("tool_calls"), list)
        for tc in m["tool_calls"]
    }
    answered = {m.get("tool_call_id") for m in model_input if m.get("role") == "tool"}
    assert declared and declared <= answered, "no dangling declaration reached the model"
    assert any(m.get("role") == "user" and m.get("content") == "A" for m in stored)


def test_resume_pairs_the_open_call_not_an_answered_sibling() -> None:
    """One round with two dialog calls — the first invalid (its guidance text
    becomes the stored result), the second open. The resume pointer must
    complete the OPEN call, not reuse the answered sibling's id (a duplicate
    result plus a dangling call is a hard provider rejection)."""
    session = _FakeSession()
    db = _FakeDB()
    ask_llm = _CapturingLLM(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "bad1",
                        "function": {
                            "name": "ask_user",
                            "arguments": json.dumps({"question": ""}),
                        },
                    },
                    {
                        "id": "ok2",
                        "function": {
                            "name": "ask_user",
                            "arguments": json.dumps({"question": "Which?", "options": ["A", "B"]}),
                        },
                    },
                ],
            }
        ]
    )
    agent1 = PrepAgent(session, ask_llm)  # type: ignore[arg-type]
    asyncio.run(_drain(agent1.chat_stream("Test these tools", db)))  # type: ignore[arg-type]

    stored = _stored(session)
    results = {m["tool_call_id"] for m in stored if m.get("role") == "tool"}
    assert results == {"bad1"}, "the invalid call stored its guidance; the valid one stays open"
    pending = next(m for m in stored if m.get("ask_pending"))
    assert any(tc.get("id") == "ok2" for tc in pending["tool_calls"]), (
        "the marker sits on the declaration owning the open call"
    )

    llm2 = _CapturingLLM([{"role": "assistant", "content": "resumed", "tool_calls": None}])  # type: ignore[arg-type]
    agent2 = PrepAgent(session, llm2)  # type: ignore[arg-type]
    asyncio.run(_drain(agent2.chat_stream("A", db)))  # type: ignore[arg-type]

    pointers = {
        m["tool_call_id"]: str(m.get("content") or "")
        for m in llm2.seen_inputs[0]
        if m.get("role") == "tool"
    }
    assert "[ask_user]" in pointers.get("ok2", ""), "the pointer completes the open call"
    assert "[ask_user]" not in pointers.get("bad1", ""), "the answered sibling keeps its own result"


def test_resume_freezes_toolset_from_the_original_task_text() -> None:
    """A resumed dialog turn keeps the ORIGINAL task's text-gated tools: the
    reply carries no repo signal, but the paused task named a repository."""
    session = _FakeSession()
    db = _FakeDB()
    ask_llm = _CapturingLLM([_ask_call("Which part?", ["Perf", "API"])])  # type: ignore[arg-type]
    agent1 = PrepAgent(session, ask_llm)  # type: ignore[arg-type]
    asyncio.run(_drain(agent1.chat_stream("Review github.com/owner/repo for me", db)))  # type: ignore[arg-type]

    llm2 = _CapturingLLM([{"role": "assistant", "content": "resumed", "tool_calls": None}])  # type: ignore[arg-type]
    agent2 = PrepAgent(session, llm2)  # type: ignore[arg-type]
    asyncio.run(_drain(agent2.chat_stream("性能", db)))  # type: ignore[arg-type]

    turn1_names = ask_llm.seen_tool_names[0]
    turn2_names = llm2.seen_tool_names[0]
    assert any(name in turn1_names for name in GITHUB_TOOL_NAMES), (
        "the task text gated the github tools into turn one"
    )
    assert any(name in turn2_names for name in GITHUB_TOOL_NAMES), (
        "the resumed turn keeps them via the original task text, not the reply"
    )
