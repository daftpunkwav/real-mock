"""InterviewRunner unit tests."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator


from realmock.platform.models import LLMSettings
from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.agents.events import EventKind
from realmock.domains.interview.agents.runner import InterviewRunner
from tests.fakes import FakeLLMClient


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
        # These tests pin the static-flow behavior: skip the background planner
        # wait by marking planning as already failed (degraded path).
        plan_status="failed",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


async def _consume(events: AsyncIterator) -> list:
    return [e async for e in events]


def _proto_tokens(say: str, **controls) -> list[str]:
    """Build say-first protocol JSON and split into chunks to simulate streaming (cross-token)."""
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
    return [text[i : i + 7] for i in range(0, len(text), 7)]


def test_stream_opening_records_first_question(db) -> None:
    """Opening turn should stream say plaintext and persist state; controls come with TURN_COMPLETE."""
    session = _make_session(db)
    say = "Hello, I am the interviewer. Please introduce yourself."
    llm = FakeLLMClient(tokens=_proto_tokens(say, wait_seconds=60))
    runner = InterviewRunner(session, llm)

    events = []
    import asyncio

    async def run():
        async for e in runner.stream_opening(db):
            events.append(e)

    asyncio.run(run())

    tokens = [e.token for e in events if e.kind == EventKind.TOKEN]
    assert "".join(tokens) == say

    turn_done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert turn_done.content == say
    assert turn_done.phase_id == "identity_check"
    assert turn_done.is_complete is False
    assert turn_done.wait_seconds == 60

    db.refresh(session)
    assert session.status == "active"
    assert session.started_at is not None
    state = json.loads(session.agent_state)
    assert state["phase_idx"] == 0
    assert state["questions_in_phase"] == 1


def test_stream_turn_plain_text_falls_back(db) -> None:
    """Non-protocol output (plain text) should degrade entirely to say without aborting the turn."""
    session = _make_session(db)
    session.agent_state = json.dumps({"phase_idx": 3, "questions_in_phase": 0})
    session.current_phase = "project_deep_dive"
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["Speak directly, ", "with no JSON structure."])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        events = []
        async for e in runner.stream_turn("My name is Zhang San", db):
            events.append(e)
        return events

    events = asyncio.run(run())
    turn_done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert turn_done.content == "Speak directly, with no JSON structure."
    assert turn_done.phase_changed is False
    assert turn_done.emotion == "neutral"


def test_stream_turn_increments_question_count(db) -> None:
    """A normal turn below max_questions should not set phase_changed."""
    session = _make_session(db)
    # Push phase_idx to project_deep_dive (max=6) to avoid auto-advance
    session.agent_state = json.dumps({"phase_idx": 3, "questions_in_phase": 0})
    session.current_phase = "project_deep_dive"
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["Okay,", "Tell me about the project you know best."])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        events = []
        async for e in runner.stream_turn("My name is Zhang San", db):
            events.append(e)
        return events

    events = asyncio.run(run())
    turn_done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert turn_done.phase_id == "project_deep_dive"
    assert turn_done.phase_changed is False

    db.refresh(session)
    state = json.loads(session.agent_state)
    assert state["questions_in_phase"] == 1


def test_stream_turn_advances_phase_on_marker(db) -> None:
    """phase_complete=true in the turn protocol should advance to the next phase."""
    session = _make_session(db)
    llm = FakeLLMClient(
        stream_sequences=[
            _proto_tokens("Hello, let me verify your identity first."),  # opening
            _proto_tokens("Okay, identity verification is complete.", phase_complete=True),  # turn
        ]
    )
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_opening(db):
            pass
        events = []
        async for e in runner.stream_turn("My name is Zhang San", db):
            events.append(e)
        return events

    events = asyncio.run(run())
    turn_done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert turn_done.phase_changed is True
    assert turn_done.phase_id == "self_intro"

    db.refresh(session)
    state = json.loads(session.agent_state)
    assert state["phase_idx"] == 1
    assert state["questions_in_phase"] == 0


def test_stream_turn_advances_phase_on_max_reached(db) -> None:
    """Reaching the phase max question count auto-advances (no protocol flag required)."""
    session = _make_session(db)
    # identity_check phase max_questions = 1
    llm = FakeLLMClient(tokens=_proto_tokens("Continue."))
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_opening(db):
            pass
        events = []
        async for e in runner.stream_turn("answer", db):
            events.append(e)
        return events

    events = asyncio.run(run())
    turn_done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert turn_done.phase_changed is True
    assert turn_done.phase_id == "self_intro"


def test_stream_turn_marks_complete_on_interview_flag(db) -> None:
    """interview_complete=true in the protocol should end the interview."""
    session = _make_session(db)
    llm = FakeLLMClient(
        tokens=_proto_tokens("The interview is over. Thank you for your time.", interview_complete=True)
    )
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        events = []
        async for e in runner.stream_turn("Last answer", db):
            events.append(e)
        return events

    events = asyncio.run(run())
    turn_done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert turn_done.is_complete is True

    db.refresh(session)
    assert session.status == "completed"
    assert session.ended_at is not None


def test_stream_turn_with_face_appends_hints(db) -> None:
    """Face-analysis hints should be appended to the LLM user message text."""
    session = _make_session(db)
    llm = FakeLLMClient(tokens=["Good."])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_turn("I'm listening", db, face={
            "face_detected": True,
            "looking_away": True,
            "nervousness": 0.8,
        }):
            pass

    asyncio.run(run())

    last_call = llm.stream_calls[-1]
    user_msg = next(m for m in reversed(last_call) if m["role"] == "user")
    assert "Face analysis" in user_msg["content"]
    assert "looking away from the camera" in user_msg["content"]
    assert "nervous" in user_msg["content"]


def test_stream_turn_emits_error_on_llm_failure(db, monkeypatch) -> None:
    """LLM failures should emit an ERROR event without crashing the turn."""
    session = _make_session(db)

    class BrokenLLM(FakeLLMClient):
        async def chat_stream(self, messages, temperature: float = 0.75, tools=None):
            raise RuntimeError("LLM unavailable")
            yield  # unreachable, but keeps mypy happy

        async def chat_message(self, messages, temperature: float = 0.7, response_format=None, tools=None, tool_choice=None):
            raise RuntimeError("LLM unavailable")

        async def chat_message_stream(self, messages, temperature: float = 0.7, tools=None):
            raise RuntimeError("LLM unavailable")
            yield  # unreachable

    runner = InterviewRunner(session, BrokenLLM())
    import asyncio

    async def run():
        events = []
        async for e in runner.stream_turn("Test", db):
            events.append(e)
        return events

    events = asyncio.run(run())
    errors = [e for e in events if e.kind == EventKind.ERROR]
    assert errors and "temporarily unavailable" in (errors[0].error or "")


def test_stream_turn_injects_followup_probe_when_vague(db) -> None:
    """Vague answers should inject follow-up guidance into LLM messages."""
    session = _make_session(db)
    # Seed the previous LLM question
    session.messages = json.dumps([
        {"role": "system", "content": "You are the interviewer"},
        {"role": "assistant", "content": "Describe a performance optimization experience"},
    ])
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["Okay."])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_turn("That's about it", db):
            pass

    asyncio.run(run())

    last_call = llm.stream_calls[-1]
    system_msgs = [m["content"] for m in last_call if m["role"] == "system"]
    assert any("Follow-up guidance" in s and "vague" in s for s in system_msgs), system_msgs


def test_stream_turn_no_followup_probe_when_solid(db) -> None:
    """Concrete answers should not inject follow-up guidance."""
    session = _make_session(db)
    session.messages = json.dumps([
        {"role": "system", "content": "You are the interviewer"},
        {"role": "assistant", "content": "Please describe the impact of the performance optimization"},
    ])
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["Good."])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_turn(
            "Endpoint RT dropped from 200 ms to 35 ms, QPS increased fivefold, and the error rate fell by 90%.",
            db,
        ):
            pass

    asyncio.run(run())

    last_call = llm.stream_calls[-1]
    system_msgs = [m["content"] for m in last_call if m["role"] == "system"]
    assert not any("Follow-up guidance" in s for s in system_msgs)


def test_stream_turn_applies_context_compression(db, api_db) -> None:
    """A small context_window should trigger context compression."""
    session = _make_session(db)
    # Seed 200 user/assistant turns to force compression
    base = [{"role": "system", "content": "You are the interviewer"}]
    base += [
        {"role": "user" if i % 2 == 0 else "assistant",
         "content": "Conversation content" * 20}
        for i in range(40)
    ]
    session.messages = json.dumps(base, ensure_ascii=False)
    settings = api_db.query(LLMSettings).filter(LLMSettings.id == 1).first()
    if settings is None:
        settings = LLMSettings(id=1, api_key="x", api_base="http://x", model="m",
                                context_window=500, max_tokens=100)
        api_db.add(settings)
    else:
        settings.context_window = 500
    api_db.commit()
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["Good."])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_turn("New answer", db):
            pass

    asyncio.run(run())

    last_call = llm.stream_calls[-1]
    # After compression, message count should be below the original
    assert len(last_call) < len(base) + 1  # +1 for new user msg
    # Should include a compression notice
    assert any("Context compression" in m.get("content", "") for m in last_call)


def test_stream_turn_injects_rag_context(db) -> None:
    """On RAG hit, retrieved snippets should be injected as system messages into the LLM call."""
    import uuid
    from pathlib import Path

    # Isolate chroma with a temp directory
    chroma_dir = Path(db.get_bind().url.database).parent / f"chroma_{uuid.uuid4().hex[:6]}"
    chroma_dir.mkdir(parents=True, exist_ok=True)


    class _StubRAG:
        def __init__(self):
            self.embed_called_with: list[str] = []

        async def query_for_company(self, query, company_id, top_k=4):
            self.embed_called_with.append(query)
            return [
                {
                    "text": f"{company_id} Style: frequent follow-up questions",
                    "metadata": {"company_id": company_id, "section": "style"},
                    "distance": 0.1,
                },
            ]

        async def query(self, query, top_k=3, company_id=None):
            return []

    rag = _StubRAG()
    session = _make_session(db)
    session.messages = json.dumps([
        {"role": "system", "content": "You are the interviewer"},
        {"role": "assistant", "content": "Please discuss performance optimization"},
    ], ensure_ascii=False)
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["Good."])
    runner = InterviewRunner(session, llm, rag=rag)

    import asyncio

    async def run():
        async for _ in runner.stream_turn("API RT decreased from 200ms to 35ms", db):
            pass

    asyncio.run(run())

    last_call = llm.stream_calls[-1]
    system_msgs = [m["content"] for m in last_call if m["role"] == "system"]
    assert any("Enterprise knowledge base search supplement" in s and "bytedance" in s for s in system_msgs), system_msgs


def test_stream_turn_skips_rag_when_no_hits(db) -> None:
    """On RAG miss, empty snippets must not be injected."""
    class _EmptyRAG:
        async def query_for_company(self, query, company_id, top_k=4):
            return []
        async def query(self, query, top_k=3, company_id=None):
            return []

    rag = _EmptyRAG()
    session = _make_session(db)
    session.messages = json.dumps([
        {"role": "system", "content": "You are the interviewer"},
        {"role": "assistant", "content": "Self-introduction"},
    ], ensure_ascii=False)
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["Good."])
    runner = InterviewRunner(session, llm, rag=rag)

    import asyncio

    async def run():
        async for _ in runner.stream_turn("My name is Zhang San", db):
            pass

    asyncio.run(run())

    last_call = llm.stream_calls[-1]
    system_msgs = [m["content"] for m in last_call if m["role"] == "system"]
    assert not any("Enterprise knowledge base" in s for s in system_msgs)


def test_stream_turn_rag_error_does_not_break_turn(db) -> None:
    """When RAG raises, the interview turn should still complete without aborting."""
    class _BrokenRAG:
        async def query_for_company(self, query, company_id, top_k=4):
            raise RuntimeError("RAG unavailable")
        async def query(self, query, top_k=3, company_id=None):
            raise RuntimeError("RAG unavailable")

    rag = _BrokenRAG()
    session = _make_session(db)
    session.messages = json.dumps([
        {"role": "system", "content": "You are the interviewer"},
        {"role": "assistant", "content": "Self-introduction"},
    ], ensure_ascii=False)
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["Okay."])
    runner = InterviewRunner(session, llm, rag=rag)

    import asyncio

    async def run():
        events = []
        async for e in runner.stream_turn("My name is Li Si", db):
            events.append(e)
        return events

    events = asyncio.run(run())
    # Expect turn_done and no error
    assert any(e.kind.value == "turn_done" for e in events)
    assert not any(e.kind.value == "error" for e in events)


def test_agent_public_methods_no_longer_underscore(db) -> None:
    """Private fields should be exposed via public methods (so ws_handler does not reach in)."""
    from realmock.domains.interview.agents.session_state import InterviewSessionState

    public = {
        "save_state", "current_phase", "phases_remaining",
        "mark_active", "mark_completed",
        "record_user_text", "record_assistant_text",
        "advance_phase_if_needed",
        "build_opening_prompt", "refresh_system_memory",
        "set_questions_in_phase", "reset_messages",
    }
    assert public.issubset(set(dir(InterviewSessionState)))


def test_refresh_system_memory_updates_asked_questions(db) -> None:
    """Each turn refreshes structured memory in the system prompt so asked_questions stays current."""
    from realmock.domains.interview.agents.session_state import InterviewSessionState

    session = _make_session(db)
    session.messages = json.dumps([
        {"role": "system", "content": "You are the interviewer"},
    ], ensure_ascii=False)
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["Good."])
    agent = InterviewSessionState(session, llm)
    # Simulate one question already asked after opening
    agent.agent_state.setdefault("asked_questions", [])
    agent.agent_state["asked_questions"].append("Please describe your Redis cache design")
    agent.refresh_system_memory()

    system_content = agent.messages[0]["content"]
    assert "Session structured memory" in system_content
    assert "Redis cache design" in system_content


def test_refresh_system_memory_replaces_old_memory(db) -> None:
    """Refresh should replace the old memory block rather than append another."""
    from realmock.domains.interview.agents.session_state import InterviewSessionState

    session = _make_session(db)
    session.messages = json.dumps([
        {"role": "system", "content": (
            "You are the interviewer\n\n"
            "## Session structured memory (do not repeat asked questions)\n"
            "Covered:\n- Previous question A"
        )},
    ], ensure_ascii=False)
    db.commit()
    db.refresh(session)

    agent = InterviewSessionState(session, FakeLLMClient())
    agent.agent_state.setdefault("asked_questions", [])
    agent.agent_state["asked_questions"] = ["New question B"]
    agent.refresh_system_memory()

    system_content = agent.messages[0]["content"]
    # Old memory replaced: no longer contains old question A; should contain new question B
    assert "Previous question A" not in system_content
    assert "New question B" in system_content
    # Must not have two memory markers
    assert system_content.count("## Session structured memory") == 1


def test_stream_turn_records_weak_point_on_followup(db) -> None:
    """Follow-up firing records the category in followup_clues but must NOT pollute weak_points with examiner guidance."""
    session = _make_session(db)
    session.messages = json.dumps([
        {"role": "system", "content": "You are the interviewer"},
        {"role": "assistant", "content": "Describe a performance optimization experience"},
    ])
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["Okay."])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_turn("That's about it", db):
            pass

    asyncio.run(run())

    db.refresh(session)
    state = json.loads(session.agent_state)
    # Guidance wording stays out of weak_points (it is an examiner instruction,
    # not a candidate weakness fact; digests and later prompts read that list).
    weak = state.get("weak_points") or []
    assert not any("[vague]" in w for w in weak), f"weak_points polluted: {weak}"
    # Real follow-up categories land in followup_clues (for system-learning stats)
    clues = state.get("followup_clues") or []
    assert "vague" in clues, f"followup_clues should contain vague: {clues}"


def test_build_opening_prompt_includes_system_learning(db, monkeypatch) -> None:
    """Opening prompt should inject the system-learning summary (growth feedback loop)."""
    from realmock.platform.contracts.lifecycle_hooks import set_system_insights_provider

    insights = {
        "avg_scores_by_company": {"bytedance": 65},
        "recent_probes": [
            {"company": "bytedance", "role": "Backend engineer",
             "point": "Insufficient understanding of cache consistency"},
        ],
    }
    set_system_insights_provider(lambda limit=10: insights)
    monkeypatch.setattr(
        "realmock.platform.contracts.lifecycle_hooks._system_insights_provider",
        lambda limit=10: insights,
    )

    session = _make_session(db)  # company=bytedance role=backend engineer
    llm = FakeLLMClient()
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_opening(db):
            pass

    asyncio.run(run())

    system_content = runner.agent.messages[0]["content"]
    # Should include system learning summary with avg score and weak-spot clues
    assert "System learning summary" in system_content
    assert "65" in system_content
    assert "cache consistency" in system_content.lower()


def test_build_opening_prompt_without_system_learning(db, monkeypatch) -> None:
    """With no system-learning data, an empty summary block must not be injected."""
    from realmock.platform.contracts.lifecycle_hooks import set_system_insights_provider

    empty = {"avg_scores_by_company": {}, "recent_probes": []}
    set_system_insights_provider(lambda limit=10: empty)
    monkeypatch.setattr(
        "realmock.platform.contracts.lifecycle_hooks._system_insights_provider",
        lambda limit=10: empty,
    )

    session = _make_session(db)
    llm = FakeLLMClient()
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_opening(db):
            pass

    asyncio.run(run())

    system_content = runner.agent.messages[0]["content"]
    assert "System learning summary" not in system_content


def test_reverse_qa_phase_injects_company_representative_prompt(db) -> None:
    """Entering reverse_qa should inject the company-representative role prompt."""

    session = _make_session(db)
    # Set phase_idx to the phase before reverse_qa (scenario) with questions_in_phase
    # at max so advance_phase_if_needed moves to reverse_qa
    session.agent_state = json.dumps({
        "phase_idx": 6,  # scenario
        "questions_in_phase": 2,  # scenario.max_questions=2
    })
    session.current_phase = "scenario"
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["Okay, let's move to your questions."])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_turn("My answer", db):
            pass

    asyncio.run(run())

    # After advancing to reverse_qa, messages should include the company-rep prompt
    system_msgs = [m["content"] for m in runner.agent.messages if m["role"] == "system"]
    reverse_qa_msg = next(
        (s for s in system_msgs if "Role switch" in s and "representative" in s), None
    )
    assert reverse_qa_msg is not None, f"company-rep prompt not found: {system_msgs}"
    # Should include company knowledge (bytedance -> ByteDance)
    assert "ByteDance" in reverse_qa_msg
    # Should stress admitting uncovered topics honestly
    assert "don't have exact information" in reverse_qa_msg


def test_non_reverse_qa_phase_uses_generic_entry_message(db) -> None:
    """Non-reverse_qa phase advances should use a generic entry cue, not company-rep."""
    session = _make_session(db)
    # identity_check(idx=0, max=1) -> advance to self_intro
    session.agent_state = json.dumps({"phase_idx": 0, "questions_in_phase": 1})
    session.current_phase = "identity_check"
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=["Okay."])
    runner = InterviewRunner(session, llm)

    import asyncio

    async def run():
        async for _ in runner.stream_turn("answer", db):
            pass

    asyncio.run(run())

    system_msgs = [m["content"] for m in runner.agent.messages if m["role"] == "system"]
    # self_intro entry should be generic and not contain Role switch
    entry_msgs = [s for s in system_msgs if "Entering new phase" in s]
    assert entry_msgs, f"expected phase-entry message: {system_msgs}"
    assert not any("Role switch" in s for s in entry_msgs)

# ── Runner tools wiring under RAG backends ──────────────────────────────


def _make_embed_settings(**overrides):
    """Minimal Settings builder (kept local to avoid coupling across test files)."""
    from realmock.platform.config import Settings

    base = {
        "llm_api_base": "https://api.stepfun.com/v1",
        "llm_api_key": "sk-test",
        "llm_model": "step-3.7-flash",
        "rag_backend": "local",
    }
    base.update(overrides)
    return Settings(**base)


def _make_session(db):
    """Use a minimal InterviewSession builder for tool-wiring tests."""
    from realmock.domains.interview.models import InterviewSession

    s = InterviewSession(
        profile_id=1,
        role="backend",
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


def test_interview_runner_collects_stepfun_tools(db) -> None:
    """When StepFun is ready, tools should include retrieval + interview function tools."""
    from realmock.domains.interview.agents.runner import InterviewRunner
    from realmock.domains.interview.capabilities.rag.stepfun_backend import StepFunRetrievalRAG

    session = _make_session(db)
    rag = StepFunRetrievalRAG(llm=FakeLLMClient(api_key="sk-test"), settings=_make_embed_settings())
    rag._vector_store_id = "1712"
    rag._ready = True

    runner = InterviewRunner(session=session, llm=FakeLLMClient(), rag=rag)
    tools = runner.tools.collect_chat_tools()
    assert tools is not None
    assert any(t.get("type") == "retrieval" for t in tools)
    # Also includes function tools such as GitHub
    assert any(
        t.get("type") == "function" and (t.get("function") or {}).get("name", "").startswith("github_")
        for t in tools
    )


def test_interview_runner_stream_tools_skip_functions(db) -> None:
    """During the streaming phase, retain only retrieval when include_function_tools=False."""
    from realmock.domains.interview.agents.runner import InterviewRunner
    from realmock.domains.interview.capabilities.rag.stepfun_backend import StepFunRetrievalRAG

    session = _make_session(db)
    rag = StepFunRetrievalRAG(llm=FakeLLMClient(api_key="sk-test"), settings=_make_embed_settings())
    rag._vector_store_id = "1712"
    rag._ready = True
    runner = InterviewRunner(session=session, llm=FakeLLMClient(), rag=rag)
    tools = runner.tools.collect_chat_tools(include_function_tools=False)
    assert tools is not None
    assert len(tools) == 1
    assert tools[0]["type"] == "retrieval"


def test_interview_runner_no_retrieval_when_rag_unready(db) -> None:
    """Function tools (GitHub, etc.) may still be available when RAG is not ready."""
    from realmock.domains.interview.agents.runner import InterviewRunner
    from realmock.domains.interview.capabilities.rag.stepfun_backend import StepFunRetrievalRAG

    session = _make_session(db)
    rag = StepFunRetrievalRAG(llm=FakeLLMClient(api_key="sk-test"), settings=_make_embed_settings())
    runner = InterviewRunner(session=session, llm=FakeLLMClient(), rag=rag)
    tools = runner.tools.collect_chat_tools()
    assert tools is not None
    assert all(t.get("type") != "retrieval" for t in tools)
    assert any((t.get("function") or {}).get("name", "").startswith("github_") for t in tools)


def test_interview_runner_function_tools_without_rag(db) -> None:
    """Expose interview function tools even without RAG."""
    from realmock.domains.interview.agents.runner import InterviewRunner

    session = _make_session(db)
    runner = InterviewRunner(session=session, llm=FakeLLMClient(), rag=None)
    tools = runner.tools.collect_chat_tools()
    assert tools is not None
    assert any((t.get("function") or {}).get("name") == "lookup_resume_projects" for t in tools)


def test_stream_turn_pace_hint_is_transient(db) -> None:
    """The pace hint reaches the LLM as a one-shot system prefix, never the persisted history."""
    import asyncio
    from datetime import datetime, timedelta, timezone

    session = _make_session(db)
    session.agent_state = json.dumps({"phase_idx": 3, "questions_in_phase": 0})
    session.current_phase = "project_deep_dive"
    session.started_at = datetime.now(timezone.utc) - timedelta(minutes=31)
    db.commit()
    db.refresh(session)

    llm = FakeLLMClient(tokens=_proto_tokens("Next question?"))
    runner = InterviewRunner(session, llm)

    async def run():
        events = []
        async for e in runner.stream_turn("My answer", db):
            events.append(e)
        return events

    events = asyncio.run(run())

    # The LLM call starts with the transient pace system hint.
    assert llm.stream_calls, "the turn must call the LLM"
    first_call = llm.stream_calls[0]
    assert first_call[0]["role"] == "system"
    assert "[Pace:" in first_call[0]["content"]

    # ...and the persisted history keeps the plain user-tail invariant.
    roles = [m.get("role") for m in runner.agent.messages]
    assert roles[-1] == "assistant"
    assert all(
        "[Pace:" not in str(m.get("content") or "")
        for m in runner.agent.messages
    )

    turn_done = next(e for e in events if e.kind == EventKind.TURN_COMPLETE)
    assert turn_done.content == "Next question?"


def test_runner_background_task_lifecycle(db) -> None:
    import asyncio
    session = _make_session(db)
    llm = FakeLLMClient()
    runner = InterviewRunner(session, llm)

    async def _dummy():
        await asyncio.sleep(10)

    async def run():
        t = runner.spawn_bg_task(_dummy())
        assert t in runner._bg_tasks
        assert not t.done()
        await runner.cancel_bg_tasks()
        assert t.cancelled()
        assert len(runner._bg_tasks) == 0

    asyncio.run(run())


def test_runner_custom_task_spawner(db) -> None:
    import asyncio
    session = _make_session(db)
    llm = FakeLLMClient()
    spawned = []

    def custom_spawner(coro):
        t = asyncio.create_task(coro)
        spawned.append(t)
        return t

    runner = InterviewRunner(session, llm, task_spawner=custom_spawner)

    async def _dummy():
        await asyncio.sleep(10)

    async def run():
        t = runner.spawn_bg_task(_dummy())
        assert t in spawned
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass

    asyncio.run(run())

