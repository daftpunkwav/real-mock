"""Prep Agent stream event sequence: status / tool_step / ask_user / usage / final answer."""

from __future__ import annotations

import asyncio
import json

import pytest

from realmock.domains.prep.agents.agent import (
    PREP_TOOL_DEFINITIONS,
    PrepAgent,
)
from realmock.domains.prep.agents.ask_user import extract_inline_ask_user, fallback_reply
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.ai.llm.usage import UsageAccumulator


class _FakeLLM:
    """Scripted chat_message replies; ``replies`` supports multi-round sequences.

    ``usage`` simulates client-side usage accumulation when the provider returns it; None means none.
    """

    def __init__(self, messages_reply=None, stream_tokens=(), replies=None, usage=None):
        if replies is not None:
            self.replies = list(replies)
        else:
            self.replies = [messages_reply] if messages_reply is not None else []
        self.calls = 0
        self.stream_calls = 0
        self.stream_tokens = list(stream_tokens)
        self.usage = usage

    async def chat_message(self, messages, temperature=0.7, tools=None, **kwargs):
        del messages, temperature, tools, kwargs
        idx = min(self.calls, len(self.replies) - 1)
        self.calls += 1
        return self.replies[idx]

    def chat_stream(self, messages, temperature=0.7, tools=None):
        del messages, temperature, tools
        self.stream_calls += 1

        async def _gen():
            for t in self.stream_tokens:
                yield t
        return _gen()


class _FakeSession:
    messages = "[]"
    resume_id = None
    target_company = ""
    token_usage = 0
    prompt_tokens = 0
    completion_tokens = 0
    cached_tokens = 0


class _FakeDB:
    def commit(self):
        pass

    def query(self, model):
        return _FakeQuery()


class _StreamFakeLLM(_FakeLLM):
    """Fake LLM with streamed tool rounds: ``rounds[i]`` is the i-th chat_message_stream event list."""

    def __init__(self, rounds=None, **kwargs):
        super().__init__(**kwargs)
        self.rounds = list(rounds or [])

    async def chat_message_stream(self, messages, temperature=0.7, tools=None, **kwargs):
        del messages, temperature, tools, kwargs
        idx = min(self.calls, len(self.rounds) - 1)
        self.calls += 1
        for event in self.rounds[idx]:
            yield event


class _FakeQuery:
    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None


def _collect(agen) -> list:
    async def run():
        return [item async for item in agen]
    return asyncio.run(run())


def test_tool_definitions_include_react_tools() -> None:
    names = {t["function"]["name"] for t in PREP_TOOL_DEFINITIONS}
    assert {"web_search", "ask_user", "take_note"} <= names


def test_chat_stream_ask_user_halts_with_event() -> None:
    llm = _FakeLLM(
        messages_reply={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "function": {
                        "name": "ask_user",
                        "arguments": json.dumps(
                            {"question": "Target role?", "options": ["Backend", "Algorithm"]},
                            ensure_ascii=False,
                        ),
                    },
                }
            ],
        }
    )
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        out = []
        async for item in agent.chat_stream("Help me plan", _FakeDB()):  # type: ignore[arg-type]
            out.append(item)
        return out

    items = asyncio.run(run())
    types = [i["type"] for i in items if isinstance(i, dict)]
    assert "status" in types and "ask_user" in types
    ask = next(i for i in items if isinstance(i, dict) and i["type"] == "ask_user")
    assert ask["question"] == "Target role?"
    assert ask["options"] == ["Backend", "Algorithm"]
    # After the dialog, only the fixed prompt is streamed — no full answer.
    # Default reply locale is zh-CN (product default) without an explicit ui_locale.
    texts = [i for i in items if isinstance(i, str)]
    assert "".join(texts) == fallback_reply("zh-CN")
    # Tool message is filled back so the message sequence stays paired
    tool_msgs = [m for m in agent.messages if m.get("role") == "tool"]
    assert tool_msgs and "Dialog shown to the user" in tool_msgs[0]["content"]
    # Persisted guidance message should include steps (with ask_user) for refresh recovery
    assistant_msgs = [m for m in agent.messages if m.get("role") == "assistant"]
    last = assistant_msgs[-1]
    assert last["content"] == fallback_reply("zh-CN")
    assert any(s["name"] == "ask_user" for s in last["steps"])


def test_chat_stream_ask_user_waiting_line_follows_ui_locale() -> None:
    """The visible waiting line matches the request ui_locale (en here)."""
    llm = _FakeLLM(
        messages_reply={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "function": {
                        "name": "ask_user",
                        "arguments": json.dumps(
                            {"question": "Target role?", "options": ["Backend", "Algorithm"]},
                            ensure_ascii=False,
                        ),
                    },
                }
            ],
        }
    )
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        out = []
        async for item in agent.chat_stream("Help me plan", _FakeDB(), ui_locale="en"):  # type: ignore[arg-type]
            out.append(item)
        return out

    items = asyncio.run(run())
    texts = [i for i in items if isinstance(i, str)]
    assert "".join(texts) == fallback_reply("en")
    assert agent.reply_locale == "en"


async def test_restored_session_refreshes_reply_locale() -> None:
    """Per-request agents must honor ui_locale even when system seeding is skipped."""
    session = _FakeSession()
    session.messages = json.dumps([{"role": "user", "content": "hi"}])
    agent = PrepAgent(session, _FakeLLM())  # type: ignore[arg-type]
    await agent._ensure_system(db=None, ui_locale="en")
    assert agent.reply_locale == "en"
    assert agent.messages == [{"role": "user", "content": "hi"}]


def test_chat_stream_early_content_sliced_not_instant() -> None:
    long_answer = "Very long direct answer" * 50
    llm = _FakeLLM(messages_reply={"role": "assistant", "content": long_answer, "tool_calls": None})
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        out = []
        async for item in agent.chat_stream("Analyze the resume", _FakeDB()):  # type: ignore[arg-type]
            out.append(item)
        return out

    items = asyncio.run(run())
    texts = [i for i in items if isinstance(i, str)]
    assert len(texts) > 3, "early content should be sliced for smooth output, not yielded at once"
    assert "".join(texts) == long_answer
    # Last persisted assistant content is complete (may be followed by a working-memory system block)
    assistant_msgs = [m for m in agent.messages if m.get("role") == "assistant"]
    assert assistant_msgs[-1]["content"] == long_answer


def test_chat_stream_clears_status_before_answer() -> None:
    long_answer = "Main text" * 30
    llm = _FakeLLM(messages_reply={"role": "assistant", "content": long_answer, "tool_calls": None})
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [
            item
            async for item in agent.chat_stream("hi", _FakeDB(), ui_locale="zh-CN")  # type: ignore[arg-type]
        ]

    items = asyncio.run(run())
    statuses = [i for i in items if isinstance(i, dict) and i["type"] == "status"]
    # Status starts with the thinking prompt (localized) and is cleared to "" before answer tokens
    assert statuses[0]["text"] == "思考中"
    assert statuses[-1]["text"] == ""
    first_text_idx = next(i for i, x in enumerate(items) if isinstance(x, str))
    assert items.index(statuses[-1]) < first_text_idx


def test_chat_stream_cancel_persists_partial_turn_as_stopped() -> None:
    """Client disconnect mid-answer must persist user + partial text with stopped=True."""
    llm = _FakeLLM(
        messages_reply={"role": "assistant", "content": None, "tool_calls": None},
        stream_tokens=["hello ", "world"],
    )
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        out = []
        gen = agent.chat_stream("hi", _FakeDB())  # type: ignore[arg-type]
        async for item in gen:
            out.append(item)
            if isinstance(item, str):
                # Simulate the stop button: close the stream after the first token.
                await gen.aclose()
                break
        return out

    items = asyncio.run(run())
    assert any(isinstance(i, str) for i in items)
    assistants = [m for m in agent.messages if m.get("role") == "assistant"]
    assert assistants and assistants[-1].get("stopped") is True
    assert "hello" in (assistants[-1].get("content") or "")
    assert any(m.get("role") == "user" and m.get("content") == "hi" for m in agent.messages)


def test_run_chat_drop_last_assistant_regenerates() -> None:
    """drop_last_assistant removes the previous reply so the turn reruns."""
    from realmock.domains.prep.agents.chat import run_chat

    llm = _FakeLLM(messages_reply={"role": "assistant", "content": "fresh", "tool_calls": None})
    session = _FakeSession()
    session.messages = json.dumps([
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "stale"},
    ])
    agent = PrepAgent(session, llm)  # type: ignore[arg-type]

    async def run():
        return await run_chat(agent, "q again", _FakeDB(), drop_last_assistant=True)  # type: ignore[arg-type]

    # Early content path returns the model text directly.
    assert asyncio.run(run()) == "fresh"
    assert "stale" not in json.dumps(agent.messages, ensure_ascii=False)


def test_chat_stream_ask_user_keeps_search_groups(monkeypatch) -> None:
    """When ask_user halts the stream, earlier search-card events must not be dropped."""

    def fake_search(query: str, max_results: int):
        return "[1] fake", [{"title": "t", "url": "https://example.com", "snippet": "s"}]

    monkeypatch.setattr(
        "realmock.platform.capabilities.ai.agent.tools.search.web_search_with_hits", fake_search
    )
    search_reply = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c0",
                "function": {
                    "name": "web_search",
                    "arguments": '{"query": "interview experiences"}',
                },
            }
        ],
    }
    ask_reply = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c1",
                "function": {
                    "name": "ask_user",
                    "arguments": '{"question": "Which one?", "options": ["A", "B"]}',
                },
            }
        ],
    }
    llm = _FakeLLM(replies=[search_reply, ask_reply])
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    types = [i["type"] for i in items if isinstance(i, dict)]
    assert "search_results" in types, "search cards before ask_user must be re-emitted"
    assert "ask_user" in types
    assert types.index("search_results") < types.index("ask_user")


def test_ask_user_options_normalizes_json_shapes() -> None:
    """When the LLM passes options as dict/pseudo-JSON, the dialog event must use clean text."""
    ask_reply = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c1",
                "function": {
                    "name": "ask_user",
                    "arguments": json.dumps(
                        {
                            "question": "Next step?",
                            "options": [
                                {"description": "Generate a set of MCP practice questions", "value": "quiz_mcp"},
                                "{description: 'Pick one project for simulated chained follow-up questions', value: 'deep_dive'}",
                                "Provide the learning roadmap directly",
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
            }
        ],
    }
    llm = _FakeLLM(messages_reply=ask_reply)
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    ask = next(i for i in items if isinstance(i, dict) and i["type"] == "ask_user")
    assert ask["options"] == [
        "Generate a set of MCP practice questions",
        "Pick one project for simulated chained follow-up questions",
        "Provide the learning roadmap directly",
    ]


def test_chat_stream_persists_steps_and_search_groups(monkeypatch) -> None:
    """Steps and search cards should persist on the assistant message for refresh recovery."""

    def fake_search(query: str, max_results: int):
        return "[1] fake", [{"title": "t", "url": "https://example.com", "snippet": "s"}]

    monkeypatch.setattr(
        "realmock.platform.capabilities.ai.agent.tools.search.web_search_with_hits", fake_search
    )
    search_reply = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c0",
                "function": {
                    "name": "web_search",
                    "arguments": '{"query": "interview experiences"}',
                },
            }
        ],
    }
    answer = "Final answer content"
    answer_reply = {"role": "assistant", "content": answer, "tool_calls": None}
    # After tool rounds, model content is sliced back as the final answer; no second tool-less generation
    llm = _FakeLLM(replies=[search_reply, answer_reply], stream_tokens=(answer,))
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    assert "".join(i for i in items if isinstance(i, str)) == answer
    assert llm.stream_calls == 0, "final answer comes from the loop return; no extra tool-less stream"

    assistant_msgs = [m for m in agent.messages if m.get("role") == "assistant"]
    last = assistant_msgs[-1]
    assert last["content"] == answer
    assert last["steps"] == [{
        "name": "web_search",
        "query": "interview experiences",
        "args": {"query": "interview experiences"},
        "result": "[web_search] interview experiences\n[1] fake",
    }]
    assert last["search_groups"][0]["query"] == "interview experiences"


def test_chat_stream_emits_thinking_event_and_persists() -> None:
    """Model reasoning is emitted as thinking events and persisted on the assistant message."""
    search_reasoning = "Record the weak points first, then decide what to retrieve."
    answer_reasoning = "Integrate the observations and formulate a coaching response."
    search_reply = {
        "role": "assistant",
        "content": None,
        "reasoning": search_reasoning,
        "tool_calls": [
            {
                "id": "c0",
                "function": {
                    "name": "take_note",
                    "arguments": '{"kind": "note", "content": "x"}',
                },
            }
        ],
    }
    answer = "Final answer content." * 40
    answer_reply = {
        "role": "assistant",
        "content": answer,
        "reasoning": answer_reasoning,
        "tool_calls": None,
    }
    llm = _FakeLLM(replies=[search_reply, answer_reply])
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    thinking_events = [
        i for i in items if isinstance(i, dict) and i["type"] == "thinking"
    ]
    assert [e["content"] for e in thinking_events] == [
        search_reasoning,
        "\n\n" + answer_reasoning,
    ], "non-stream full reasoning is emitted per round; round 2 starts with an inter-round separator"
    # Thinking events precede answer tokens
    first_text_idx = next(i for i, x in enumerate(items) if isinstance(x, str))
    assert items.index(thinking_events[0]) < first_text_idx

    assistant_msgs = [m for m in agent.messages if m.get("role") == "assistant"]
    last = assistant_msgs[-1]
    assert last["content"] == answer
    assert search_reasoning in last["thinking"]
    assert answer_reasoning in last["thinking"]


def test_chat_stream_rounds_stream_thinking_deltas_and_persist() -> None:
    """Streamed tool rounds: thinking deltas emit chunk-by-chunk (with inter-round separators)."""
    answer = "Final answer content." * 40
    llm = _StreamFakeLLM(
        rounds=[
            [
                {"type": "reasoning", "text": "Note this first"},
                {"type": "reasoning", "text": "Record key points"},
                {
                    "type": "message",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c0",
                                "type": "function",
                                "function": {
                                    "name": "take_note",
                                    "arguments": '{"kind": "note", "content": "x"}',
                                },
                            }
                        ],
                    },
                },
            ],
            [
                {"type": "reasoning", "text": "Structure the answer"},
                {
                    "type": "message",
                    "message": {"role": "assistant", "content": answer},
                },
            ],
        ]
    )
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    thinking_events = [
        i for i in items if isinstance(i, dict) and i["type"] == "thinking"
    ]
    assert [e["content"] for e in thinking_events] == [
        "Note this first",
        "Record key points",
        "\n\nStructure the answer",
    ], "thinking deltas should emit chunk-by-chunk; round 2 starts with an inter-round separator"
    first_text_idx = next(i for i, x in enumerate(items) if isinstance(x, str))
    assert items.index(thinking_events[0]) < first_text_idx
    assert "".join(i for i in items if isinstance(i, str)) == answer

    assistant_msgs = [m for m in agent.messages if m.get("role") == "assistant"]
    last = assistant_msgs[-1]
    assert last["content"] == answer
    # Persistence path: join by round without the display-only separator prefix
    assert last["thinking"] == "Note this firstRecord key points\n\nStructure the answer"
    assert any(s["name"] == "take_note" for s in last["steps"])


def test_chat_stream_short_preamble_gets_drift_retry() -> None:
    """Short tool-less preamble: loop injects one drift-retry; if the model persists, treat as final answer."""
    preamble = "I will search recent interview experiences in parallel and compile the most frequent topics."
    llm = _FakeLLM(replies=[{"role": "assistant", "content": preamble, "tool_calls": None}])
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    text = "".join(i for i in items if isinstance(i, str))
    assert text == preamble, "after drift-retry, a short preamble alone is still the final answer"
    assert llm.calls == 2, "short preamble triggers exactly one drift-retry, not a loop"
    assert llm.stream_calls == 0


def test_chat_stream_final_content_no_extra_llm_call() -> None:
    """Regression: when the model returns content after tool rounds,
    do not drop it and start a second tool-less generation (that path resurfaces inline-tool drift).
    Post-tool closing content is a valid final answer even if short — no drift-retry."""
    search_reply = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c0",
                "function": {
                    "name": "take_note",
                    "arguments": '{"kind": "note", "content": "x"}',
                },
            }
        ],
    }
    drifting_reply = {
        "role": "assistant",
        "content": "I need to confirm two key decisions with you before continuing:",
        "tool_calls": None,
    }
    llm = _FakeLLM(replies=[search_reply, drifting_reply], stream_tokens=())
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    text = "".join(i for i in items if isinstance(i, str))
    assert text == "I need to confirm two key decisions with you before continuing:"
    assert llm.calls == 2
    assert llm.stream_calls == 0


def test_chat_stream_inline_ask_user_rescued_as_modal() -> None:
    """When ask_user is inlined as XML in content, rescue it as a dialog event instead of silent scrub."""
    search_reply = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c0",
                "function": {
                    "name": "take_note",
                    "arguments": '{"kind": "note", "content": "x"}',
                },
            }
        ],
    }
    inline = (
        "I need to confirm two key decisions with you before continuing:\n\n"
        '<tool_call>{"name": "ask_user", "arguments": '
        '{"question": "Which project should we discuss first?", "options": ["agent-pulse", "agent-forge"]}}</tool_call>'
    )
    drifting_reply = {"role": "assistant", "content": inline, "tool_calls": None}
    llm = _FakeLLM(replies=[search_reply, drifting_reply])
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    asks = [i for i in items if isinstance(i, dict) and i["type"] == "ask_user"]
    assert len(asks) == 1, "inline ask_user must become a dialog event"
    assert asks[0]["question"] == "Which project should we discuss first?"
    assert asks[0]["options"] == ["agent-pulse", "agent-forge"]
    # Keep the guidance text, strip the tool XML block; persisted content matches display
    text = "".join(i for i in items if isinstance(i, str))
    assert "two key decisions" in text.lower()
    assert "<tool_call>" not in text
    assistant_msgs = [m for m in agent.messages if m.get("role") == "assistant"]
    assert assistant_msgs[-1]["content"] == text


def test_chat_stream_emits_usage_event_and_persists() -> None:
    """When the provider returns usage: emit a usage event at stream end and accumulate on the session."""
    usage = UsageAccumulator()
    usage.prompt_tokens = 900
    usage.completion_tokens = 120
    usage.cached_tokens = 700
    llm = _FakeLLM(
        messages_reply={"role": "assistant", "content": "Direct answer", "tool_calls": None},
        usage=usage,
    )
    session = _FakeSession()
    agent = PrepAgent(session, llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    usage_events = [i for i in items if isinstance(i, dict) and i["type"] == "usage"]
    assert len(usage_events) == 1
    assert usage_events[0]["prompt_tokens"] == 900
    assert usage_events[0]["completion_tokens"] == 120
    assert usage_events[0]["cached_tokens"] == 700
    assert session.prompt_tokens == 900
    assert session.completion_tokens == 120
    assert session.cached_tokens == 700
    assert session.token_usage > 0


def test_chat_stream_without_usage_reports_no_usage_event() -> None:
    """When the provider omits usage: no usage event and no session stats written (unknown, not zero)."""
    llm = _FakeLLM(
        messages_reply={"role": "assistant", "content": "Direct answer", "tool_calls": None},
        usage=None,
    )
    session = _FakeSession()
    agent = PrepAgent(session, llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    assert not [i for i in items if isinstance(i, dict) and i["type"] == "usage"]
    assert session.prompt_tokens == 0


@pytest.mark.asyncio
async def test_execute_short_circuits_duplicate_tool_calls(monkeypatch) -> None:
    """Same-arg tool calls in one turn short-circuit; failed calls are not cached."""
    calls: list[str] = []

    def fake_search(query: str, max_results: int):
        calls.append(query)
        return "[1] fake", []

    monkeypatch.setattr(
        "realmock.platform.capabilities.ai.agent.tools.search.web_search_with_hits", fake_search
    )
    agent = PrepAgent(_FakeSession(), _FakeLLM(messages_reply={"role": "assistant", "content": "x"}))  # type: ignore[arg-type]
    execute = agent._build_execute(_FakeDB(), [], None, None)

    first = await execute("web_search", {"query": "Interview notes"})
    second = await execute("web_search", {"query": "Interview notes"})
    third = await execute("web_search", {"query": "React interview notes"})

    assert calls == ["Interview notes", "React interview notes"], "same args should execute only once"
    assert "Duplicate call" in second and "Duplicate call" not in first
    assert "Duplicate call" not in third


@pytest.mark.asyncio
async def test_execute_failed_call_not_cached(monkeypatch) -> None:
    """Timed-out calls auto-retry (new semantics); after recovery the success is
    cached, so a same-arg re-issue is answered from the dedupe cache."""
    attempts: list[str] = []

    import asyncio as _asyncio

    def slow_search(query: str, max_results: int):
        attempts.append(query)
        if len(attempts) == 1:
            raise _asyncio.TimeoutError()
        return "[1] ok", []

    monkeypatch.setattr(
        "realmock.platform.capabilities.ai.agent.tools.search.web_search_with_hits", slow_search
    )
    agent = PrepAgent(_FakeSession(), _FakeLLM(messages_reply={"role": "assistant", "content": "x"}))  # type: ignore[arg-type]
    execute = agent._build_execute(_FakeDB(), [], None, None)

    first = await execute("web_search", {"query": "Interview notes"})
    second = await execute("web_search", {"query": "Interview notes"})

    # Attempt 1 timed out, attempt 2 (automatic retry) succeeded.
    assert attempts == ["Interview notes", "Interview notes"]
    assert "[1] ok" in first and "timed out" not in first
    assert "Duplicate call skipped" in second


@pytest.mark.asyncio
async def test_prep_function_calling_round(db, monkeypatch):
    """PrepAgent uses chat_message tool_calls instead of extracting JSON with regex."""
    from realmock.domains.prep.agents.agent import PrepAgent
    from realmock.domains.prep.models import PrepSession

    session = PrepSession(
        target_role="Backend",
        target_company="bytedance",
        access_token="t",
        messages="[]",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    calls = {"n": 0}

    class FakeLLM:
        async def chat_message(self, messages, temperature=0.7, tools=None, tool_choice=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "company_info",
                                "arguments": '{"company":"bytedance"}',
                            },
                        }
                    ],
                }
            return {"role": "assistant", "content": "Coaching based on company knowledge", "tool_calls": None}

        async def chat(self, messages, temperature=0.7, tools=None):
            return "Final coaching response"

        async def chat_stream(self, messages, temperature=0.7, tools=None):
            yield "Final"
            yield "Coaching"

    agent = PrepAgent(session, FakeLLM())  # type: ignore[arg-type]
    reply = await agent.chat("Help me prepare for a ByteDance interview", db)
    assert "Coaching" in reply or "Final" in reply
    assert calls["n"] >= 1


def _note_tool_round() -> dict:
    """One pre-tool LLM round: a take_note call with no body text."""
    return {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c0",
                    "type": "function",
                    "function": {"name": "take_note", "arguments": '{"kind": "note", "content": "x"}'},
                }
            ],
        },
    }


def _token_dicts(items: list) -> list[str]:
    """Concatenated content of dict-shaped token events (speculative streaming)."""
    return "".join(
        i["content"] for i in items if isinstance(i, dict) and i.get("type") == "token"
    )


def test_chat_stream_speculative_content_streams_as_tokens() -> None:
    """Content deltas stream live as token events during the loop; the final answer is not replayed."""
    answer = "Final answer body"
    llm = _StreamFakeLLM(
        rounds=[
            [
                {"type": "text", "text": "Let me note that. "},
                {
                    "type": "message",
                    "message": {
                        "role": "assistant",
                        "content": "Let me note that. ",
                        "tool_calls": [
                            {
                                "id": "c0",
                                "type": "function",
                                "function": {"name": "take_note", "arguments": '{"kind": "note", "content": "x"}'},
                            }
                        ],
                    },
                },
            ],
            [
                {"type": "text", "text": "Final "},
                {"type": "text", "text": "answer body"},
                {"type": "message", "message": {"role": "assistant", "content": answer}},
            ],
        ]
    )
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    # Pre-tool narration ("Let me note that. ") stays buffered (drift-safe);
    # the post-tool final answer streams live and is not replayed.
    assert _token_dicts(items) == "Final answer body"
    assert not [i for i in items if isinstance(i, str)]
    assert llm.stream_calls == 0
    assistant_msgs = [m for m in agent.messages if m.get("role") == "assistant"]
    assert assistant_msgs[-1]["content"] == answer


def test_chat_stream_first_content_token_clears_status() -> None:
    """The thinking status line is cleared by the first speculative token, not after the loop."""
    llm = _StreamFakeLLM(
        rounds=[
            [_note_tool_round()],
            [
                {"type": "text", "text": "Answer text"},
                {"type": "message", "message": {"role": "assistant", "content": "Answer text"}},
            ],
        ]
    )
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB(), ui_locale="zh-CN")]  # type: ignore[arg-type]

    items = asyncio.run(run())
    first_token_idx = next(
        i for i, x in enumerate(items) if isinstance(x, dict) and x.get("type") == "token"
    )
    statuses_before = [
        x for x in items[:first_token_idx]
        if isinstance(x, dict) and x.get("type") == "status"
    ]
    assert statuses_before and statuses_before[-1]["text"] == ""
    assert statuses_before[0]["text"] == "思考中"


@pytest.mark.asyncio
async def test_chat_stream_propagates_tool_round_error(monkeypatch) -> None:
    """A business error escaping the tool rounds surfaces (SSE error path), never a silent tool-less answer."""
    from realmock.platform.core.errors import ApiBusinessError, ErrorSpec

    agent = PrepAgent(_FakeSession(), _FakeLLM())  # type: ignore[arg-type]

    async def boom(*args, **kwargs):
        raise ApiBusinessError(
            ErrorSpec("T0000", 429, "quota exhausted", "try later", True),
            message="quota exhausted",
        )

    monkeypatch.setattr(agent, "_run_tool_rounds", boom)
    with pytest.raises(ApiBusinessError):
        async for _ in agent.chat_stream("hi", _FakeDB()):  # type: ignore[arg-type]
            pass


def test_chat_stream_empty_polished_early_falls_back_to_live_stream() -> None:
    """Early text that sanitizes to nothing (invalid inline ask_user block) must not end the turn empty."""
    llm = _FakeLLM(
        replies=[{
            "role": "assistant",
            "content": '<tool_call>{"name": "ask_user", "arguments": {"question": "", "options": ["A", "B"]}}</tool_call>',
            "tool_calls": None,
        }],
        stream_tokens=("Recovered closing answer",),
    )
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    text = "".join(i for i in items if isinstance(i, str))
    assert text == "Recovered closing answer", "a live closing stream replaces the empty turn"
    assert llm.stream_calls == 1


def test_chat_stream_inline_ask_with_empty_body_shows_waiting_line() -> None:
    """A rescued dialog from an otherwise-empty body still lands the waiting line."""
    llm = _FakeLLM(
        replies=[{
            "role": "assistant",
            "content": (
                '<tool_call>{"name": "ask_user", "arguments": '
                '{"question": "Which one?", "options": ["A", "B"]}}</tool_call>'
            ),
            "tool_calls": None,
        }]
    )
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    assert any(isinstance(i, dict) and i.get("type") == "ask_user" for i in items)
    assert "".join(i for i in items if isinstance(i, str)) == fallback_reply("zh-CN")


def test_run_chat_clears_stale_pending_quiz() -> None:
    """A quiz left pending by the previous turn is cleared at turn start (question lives in history)."""
    llm = _FakeLLM(messages_reply={"role": "assistant", "content": "reviewed", "tool_calls": None})
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]
    agent.memory.pending_quiz = "open:what is a race condition?"

    asyncio.run(agent.chat("here is my answer", _FakeDB()))  # type: ignore[arg-type])

    assert agent.memory.pending_quiz == ""
    assert "Pending quiz" not in json.dumps(agent.messages, ensure_ascii=False)


def test_display_filter_mirrors_polish_final() -> None:
    """Chunked display-filter output must equal polish_final's text exactly —
    what the user reads live is what persistence will keep (no refresh rewrite)."""
    from realmock.domains.prep.agents.chat import polish_final
    from realmock.domains.prep.agents.streaming import DisplayTextFilter

    samples = [
        "plain coaching text",
        "emoji kept \U0001F600 and kaomoji (\uff61\u25d5\u203f\u25d5\uff61)",
        "<|minimax|> template token stripped",
        'prose <tool_call><invoke name="quiz">hello <question>Q?</question></invoke></tool_call> tail',
        'bad <tool_call>{"name": "ask_user", "arguments": {"question": "Q?", "options": ["A", "B"]}}</tool_call> tail',
        "special <|x|> mixed <tool_call><invoke name=\"t\">{}</invoke></tool_call> end",
    ]
    for text in samples:
        f = DisplayTextFilter()
        out = "".join(f.feed(text[k:k + 7]) for k in range(0, len(text), 7)) + f.flush()
        expected, _ = polish_final(text)
        assert out == expected, f"mirror mismatch for: {text!r}"


def test_chat_stream_speculative_json_ask_block_not_flashed() -> None:
    """A JSON-style ask_user drift block never reaches the live token stream;
    the dialog event comes from the final-answer rescue instead."""
    block = '<tool_call>{"name": "ask_user", "arguments": {"question": "Q?", "options": ["A", "B"]}}</tool_call>'
    llm = _StreamFakeLLM(
        rounds=[
            [_note_tool_round()],
            [
                {"type": "text", "text": "before " + block},
                {"type": "message", "message": {"role": "assistant", "content": "before " + block}},
            ],
        ]
    )
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    assert _token_dicts(items) == "before ", "drift block must not flash in the live stream"
    asks = [i for i in items if isinstance(i, dict) and i.get("type") == "ask_user"]
    assert len(asks) == 1 and asks[0]["question"] == "Q?"
    assistant_msgs = [m for m in agent.messages if m.get("role") == "assistant"]
    assert assistant_msgs[-1]["content"] == "before", "persisted body strips the block too"


def test_chat_stream_speculative_keeps_emojis_like_persistence() -> None:
    """Emojis survive both the live stream and persistence (no refresh rewrite)."""
    text = "Keep focus \U0001F600 then answer"
    llm = _StreamFakeLLM(
        rounds=[
            [_note_tool_round()],
            [
                {"type": "text", "text": text},
                {"type": "message", "message": {"role": "assistant", "content": text}},
            ],
        ]
    )
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    assert _token_dicts(items) == text
    assistant_msgs = [m for m in agent.messages if m.get("role") == "assistant"]
    assert assistant_msgs[-1]["content"] == text


# ── Multi-question dialogs (1–8 per ask_user call) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_multi_question_event_shape() -> None:
    """Two questions in one call: flat fields mirror the FIRST question and the
    questions array carries every dialog; the loop still halts."""
    from realmock.domains.prep.agents.ask_user import dispatch_ask_user
    from realmock.platform.capabilities.ai.agent.loop import AgentHalt

    memory = WorkingMemory()
    queue: asyncio.Queue = asyncio.Queue()
    with pytest.raises(AgentHalt):
        await dispatch_ask_user(
            args={
                "questions": [
                    {"question": "Target role?", "options": ["Backend", "Algorithm"]},
                    {"question": "Weekly hours?", "widget": "slider", "scale": {"min": 1, "max": 40}},
                ],
            },
            memory=memory,
            events=queue,
        )
    event = queue.get_nowait()
    assert event["type"] == "ask_user"
    assert event["question"] == "Target role?", "flat fields mirror the first question"
    assert event["options"] == ["Backend", "Algorithm"]
    assert [q["question"] for q in event["questions"]] == ["Target role?", "Weekly hours?"]
    assert event["questions"][1]["widget"] == "slider"
    assert any("Asked user: Target role? | Weekly hours?" in n for n in memory.notes)


@pytest.mark.asyncio
async def test_dispatch_single_question_event_unchanged() -> None:
    """Flat shorthand stays byte-compatible: no questions key on single-question dialogs."""
    from realmock.domains.prep.agents.ask_user import dispatch_ask_user
    from realmock.platform.capabilities.ai.agent.loop import AgentHalt

    queue: asyncio.Queue = asyncio.Queue()
    with pytest.raises(AgentHalt):
        await dispatch_ask_user(
            args={"question": "Which one?", "options": ["A", "B"]},
            memory=WorkingMemory(),
            events=queue,
        )
    event = queue.get_nowait()
    assert event["question"] == "Which one?"
    assert "questions" not in event


@pytest.mark.asyncio
async def test_dispatch_clamps_and_skips_invalid_questions() -> None:
    """Beyond 8 questions only the first 8 survive; invalid ones are skipped;
    all-invalid arguments answer with the args-incomplete observation."""
    from realmock.domains.prep.agents.ask_user import dispatch_ask_user
    from realmock.platform.capabilities.ai.agent.loop import AgentHalt

    memory = WorkingMemory()
    many = [{"question": f"Q{i}?", "options": ["A", "B"]} for i in range(9)]
    many.insert(3, {"not": "a question"})
    queue: asyncio.Queue = asyncio.Queue()
    with pytest.raises(AgentHalt):
        await dispatch_ask_user(args={"questions": many}, memory=memory, events=queue)
    event = queue.get_nowait()
    assert len(event["questions"]) == 8
    assert [q["question"] for q in event["questions"]] == [f"Q{i}?" for i in range(8)]

    dead = await dispatch_ask_user(
        args={"questions": [{"options": ["A"]}, "junk"]},
        memory=WorkingMemory(),
    )
    assert "args incomplete" in dead


def test_extract_inline_collects_multiple_ask_blocks() -> None:
    """Two inline ask_user blocks merge into one dialog event with two questions;
    unparseable blocks are stripped without contributing."""
    body = (
        "Choose:\n\n"
        '<tool_call>{"name": "ask_user", "arguments": {"question": "Q1?", "options": ["A", "B"]}}</tool_call>\n\n'
        '<tool_call>{"name": "ask_user", "arguments": {"question": "", "options": ["X", "Y"]}}</tool_call>\n\n'
        '<tool_call>{"name": "ask_user", "arguments": {"question": "Q2?", "options": ["C", "D"]}}</tool_call>'
    )
    cleaned, event = extract_inline_ask_user(body)
    assert "<tool_call>" not in cleaned
    assert event is not None
    assert event["question"] == "Q1?"
    assert [q["question"] for q in event["questions"]] == ["Q1?", "Q2?"]


def test_chat_stream_finishes_with_streamed_text_when_loop_dies() -> None:
    """Speculative tokens already streamed: a later LLM-round failure finishes the
    turn with the streamed text instead of regenerating (no on-screen repeat)."""
    streamed_text = "Partial streamed answer about caching."
    llm = _StreamFakeLLM(
        rounds=[
            [_note_tool_round()],
            [
                {"type": "text", "text": streamed_text},
                {"type": "message", "message": {"role": "assistant", "content": streamed_text}},
            ],
        ]
    )

    # Round 3's LLM call explodes: the loop breaks with final_content=None.
    async def chat_message_stream(self, messages, temperature=0.7, tools=None, **kwargs):
        del messages, temperature, tools, kwargs
        idx = min(self.calls, 1)  # third call reuses the last scripted round index
        self.calls += 1
        if idx >= 2:
            raise RuntimeError("llm round failed")
        for event in self.rounds[idx]:
            yield event

    llm.calls = 0
    llm.chat_message_stream = chat_message_stream.__get__(llm)

    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return [item async for item in agent.chat_stream("hi", _FakeDB())]  # type: ignore[arg-type]

    items = asyncio.run(run())
    text = "".join(i for i in items if isinstance(i, str)) + _token_dicts(items)
    assert streamed_text in text
    assert text.count(streamed_text) == 1, "no regenerated duplicate after streamed content"
    assert llm.stream_calls == 0, "fallback regeneration must not run once content streamed"
    assistant_msgs = [m for m in agent.messages if m.get("role") == "assistant"]
    assert streamed_text in (assistant_msgs[-1].get("content") or ""), "persisted text matches what was heard"
