"""Tool-round speculative streaming: post-tool say tokens stream live through the say-first protocol.

Pins the contract between the platform loop's ``on_content`` gating (post-tool
rounds only) and the interview turn pipeline: streamed turns reuse the parser's
control fields without re-emitting the say text; a direct pre-tool answer stays
on the buffered early path (single burst, drift-safe).
"""

from __future__ import annotations

import asyncio
import json

from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.agents.events import EventKind
from realmock.domains.interview.agents.interviewer.runner import InterviewRunner
from tests.fakes import FakeLLMClient


class _RoundStreamLLM(FakeLLMClient):
    """``chat_message_stream`` yields scripted event lists per round."""

    def __init__(self, rounds: list[list[dict]], **kwargs):
        super().__init__(**kwargs)
        self.rounds = rounds

    async def chat_message_stream(self, messages, temperature=0.7, tools=None, **kwargs):
        del messages, temperature, tools, kwargs
        idx = min(self._stream_round, len(self.rounds) - 1)
        self._stream_round += 1
        for event in self.rounds[idx]:
            yield event


def _make_session(db) -> InterviewSession:
    s = InterviewSession(
        profile_id=1,
        role="Backend engineer",
        level="Mid-level engineer",
        company="bytedance",
        workflow_type="technical",
        personality="professional",
        strictness=3,
        interview_style="deep_dive",
        avatar_id="professional_male",
        scene_id="meeting_room",
        status="pending",
        current_phase="identity_check",
        plan_status="failed",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _proto_chunks(say: str, **controls) -> list[str]:
    """Say-first protocol JSON split into text deltas (simulates cross-token streaming)."""
    payload = {
        "say": say,
        "v": 1,
        "wait_seconds": 30,
        "emotion": "neutral",
        "phase_complete": False,
        "interview_complete": False,
        "turn_score": None,
        "probe": None,
        "sources": [],
    }
    payload.update(controls)
    text = json.dumps(payload, ensure_ascii=False)
    return [text[i : i + 9] for i in range(0, len(text), 9)]


_TOOL_ROUND = [
    {"type": "text", "text": "Let me look up the company profile first."},
    {
        "type": "message",
        "message": {
            "role": "assistant",
            "content": "Let me look up the company profile first.",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {
                        "name": "lookup_company_profile",
                        "arguments": '{"company": "bytedance"}',
                    },
                }
            ],
        },
    },
]


def _run(db, session, llm) -> list:
    async def run():
        events = []
        async for e in llm_runner(db, session, llm):
            events.append(e)
        return events

    def llm_runner(db, session, llm):
        return InterviewRunner(session, llm).stream_turn("My name is Zhang San", db)

    return asyncio.run(run())


def test_stream_turn_streams_post_tool_say_live(db) -> None:
    """After a tool round, the say-first answer streams as multiple TOKEN events;
    the pre-tool narration never reaches the stream and controls still land."""
    session = _make_session(db)
    say = "Thanks for the introduction. Let us talk about your cache project."
    chunks = _proto_chunks(say, wait_seconds=45)
    llm = _RoundStreamLLM(
        rounds=[
            _TOOL_ROUND,
            [{"type": "text", "text": c} for c in chunks]
            + [{"type": "message", "message": {"role": "assistant", "content": "".join(chunks)}}],
        ]
    )
    runner = InterviewRunner(session, llm)

    async def run():
        events = []
        async for e in runner.stream_turn("My name is Zhang San", db):
            events.append(e)
        return events

    events = asyncio.run(run())
    tokens = [e.token for e in events if e.kind == EventKind.TOKEN]
    assert len(tokens) > 1, "post-tool say streams as multiple tokens, not one burst"
    assert "".join(tokens) == say
    assert all("Let me look up" not in t for t in tokens), "pre-tool narration stays buffered"
    turn_done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert turn_done.content == say
    assert turn_done.wait_seconds == 45, "control fields come from the streamed protocol parse"
    # The tool ran and was ledgered alongside the streamed reply.
    state = json.loads(session.agent_state)
    assert any(t["tool"] == "lookup_company_profile" for t in state.get("tool_trace", []))


def test_stream_turn_direct_answer_stays_single_burst(db) -> None:
    """A round-0 direct answer (no tools) keeps the buffered early path: exactly
    one TOKEN event, no speculative streaming (drift-safe gating)."""
    session = _make_session(db)
    say = "Hello, please introduce yourself first."
    chunks = _proto_chunks(say)
    llm = _RoundStreamLLM(
        rounds=[
            [{"type": "message", "message": {"role": "assistant", "content": "".join(chunks)}}],
        ]
    )
    runner = InterviewRunner(session, llm)

    async def run():
        events = []
        async for e in runner.stream_turn("My name is Zhang San", db):
            events.append(e)
        return events

    events = asyncio.run(run())
    tokens = [e.token for e in events if e.kind == EventKind.TOKEN]
    assert tokens == [say], "early content burst-emits exactly one token"
    turn_done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert turn_done.content == say


def test_stream_turn_resets_parser_across_content_rounds(db) -> None:
    """A narration round (say-first JSON + tool_calls) must not close the parser:
    the next round's final answer streams and its controls win the turn."""
    session = _make_session(db)
    narr = json.dumps({"say": "Let me check the profile first.", "v": 1}, ensure_ascii=False)
    final_say = "Here is the real question about caching."
    final_json = json.dumps({
        "say": final_say, "v": 1, "wait_seconds": 20, "emotion": "neutral",
        "phase_complete": False, "interview_complete": False,
        "turn_score": None, "probe": None, "sources": [],
    }, ensure_ascii=False)
    chunks = [final_json[i:i + 9] for i in range(0, len(final_json), 9)]
    llm = _RoundStreamLLM(
        rounds=[
            [
                {"type": "text", "text": narr},
                {
                    "type": "message",
                    "message": {
                        "role": "assistant",
                        "content": narr,
                        "tool_calls": [
                            {"id": "c1", "type": "function",
                             "function": {"name": "lookup_company_profile", "arguments": "{}"}}
                        ],
                    },
                },
            ],
            [
                {"type": "text", "text": c} for c in chunks
            ] + [{"type": "message", "message": {"role": "assistant", "content": final_json}}],
        ]
    )
    runner = InterviewRunner(session, llm)

    async def run():
        events = []
        async for e in runner.stream_turn("My name is Zhang San", db):
            events.append(e)
        return events

    events = asyncio.run(run())
    tokens = [e.token for e in events if e.kind == EventKind.TOKEN]
    joined = "".join(tokens)
    assert final_say in joined, "the final round's say must stream after the parser reset"
    turn_done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert turn_done.wait_seconds == 20, "controls come from the FINAL round's protocol parse"
