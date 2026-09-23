"""Review agent tests for src/realmock/domains/resume/agents/review.py.

Covers: _parsed_dict/_query_from_args/_content_as_text/evidence_for_repair/
finalize_review_json/_reinsert_first_user/_vision_notice_message/
_restore_max_tokens/_merge_search_queries_used/_attach_review_audit/
_request_forced_final_answer/_build_tool_executor/build_resume_snapshot/
build_review_bundle/run_resume_review success/reminder/notice/error/forced-answer
branches (LLM/loop mocked).
Conventions: no real network/model downloads (all clients mocked); faked LLM/DB;
rate limits reset per test.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()


def _resume_row(**kwargs):
    from realmock.platform.models import Resume

    kwargs.setdefault("filename", "a.pdf")
    kwargs.setdefault("file_type", "pdf")
    kwargs.setdefault("raw_text", "body")
    kwargs.setdefault("parsed_profile", "{}")
    return Resume(**kwargs)


def test_parsed_dict_edges() -> None:
    from realmock.domains.resume.agents.review import _parsed_dict

    assert _parsed_dict(_resume_row(parsed_profile='{"a":1}')) == {"a": 1}
    assert _parsed_dict(_resume_row(parsed_profile="not-json")) == {}
    assert _parsed_dict(_resume_row(parsed_profile="[1,2]")) == {}
    assert _parsed_dict(_resume_row(parsed_profile=None)) == {}


def test_query_from_args_fallback() -> None:
    from realmock.domains.resume.agents.review import _query_from_args

    assert _query_from_args("web_search", {"query": "python jobs"}) == "python jobs"
    assert _query_from_args("my_tool", {}) == "my_tool"
    assert _query_from_args("t", {"query": ""}) == "t"
    assert _query_from_args("t", {"section": "edu"}) == "edu"


def test_content_as_text_variants() -> None:
    from realmock.domains.resume.agents.review import _content_as_text

    assert _content_as_text("plain") == "plain"
    assert _content_as_text(None) == ""
    out = _content_as_text([123, {"text": " hi "}, {"type": "image_url", "image_url": {"url": "data:x"}}, {"image_url": "y"}])
    assert "123" in out
    assert "hi" in out
    assert "[attached page image]" in out
    assert "data:x" not in out


def test_evidence_truncation_and_draft() -> None:
    from realmock.domains.resume.agents.review import evidence_for_repair

    big = "x" * 50000
    blob = evidence_for_repair([{"role": "user", "content": big}], big)
    assert "truncated" in blob
    assert blob.startswith("RESUME_OVERVIEW:")
    only_draft = evidence_for_repair([], "draft-text")
    assert "DRAFT:" in only_draft
    assert evidence_for_repair([], "") == ""


@pytest.mark.asyncio
async def test_finalize_evidence_empty_and_repair_failures(monkeypatch) -> None:
    from realmock.domains.resume.agents.review import finalize_review_json
    from realmock.platform.capabilities.ai.agent import LoopResult
    from realmock.platform.core.errors import ApiBusinessError

    class _LLM:
        async def chat(self, *a, **k):
            return "c"

        async def chat_json(self, *a, **k):
            return {"ok": 1}

    # evidence empty -> C0001 (tool used but no user/tool evidence and empty draft)
    loop = LoopResult(messages=[{"role": "system", "content": "sys"}], final_content="", tool_used=True)
    with pytest.raises(ApiBusinessError) as exc:
        await finalize_review_json(loop, _LLM(), locale="en", max_output=512)  # type: ignore[arg-type]
    assert exc.value.error_code == "C0001"

    # repair raises -> C0002
    class _BoomLLM:
        async def chat_json(self, *a, **k):
            raise RuntimeError("llm-down")

    loop2 = LoopResult(messages=[{"role": "user", "content": "overview-text"}], final_content="bad", tool_used=True)
    with pytest.raises(ApiBusinessError) as exc2:
        await finalize_review_json(loop2, _BoomLLM(), locale="en", max_output=512)  # type: ignore[arg-type]
    assert exc2.value.error_code == "C0002"

    # repair returns non-dict -> C0002
    class _StrLLM:
        async def chat_json(self, *a, **k):
            return "not-a-dict"

    with pytest.raises(ApiBusinessError) as exc3:
        await finalize_review_json(loop2, _StrLLM(), locale="en", max_output=512)  # type: ignore[arg-type]
    assert exc3.value.error_code == "C0002"


def test_reinsert_first_user_branches() -> None:
    from realmock.domains.resume.agents.review import _reinsert_first_user

    assert _reinsert_first_user([], [{"role": "system", "content": "s"}]) == [{"role": "system", "content": "s"}]
    first = {"role": "user", "content": "u"}
    compacted = [first, {"role": "assistant", "content": "a"}]
    assert _reinsert_first_user([first], compacted) is compacted
    out = _reinsert_first_user(
        [{"role": "system", "content": "s0"}, first],
        [{"role": "system", "content": "s0"}, {"role": "assistant", "content": "a"}],
    )
    assert out[1] == first
    out2 = _reinsert_first_user([first], [{"role": "assistant", "content": "a"}])
    assert out2[0] == first


def test_vision_notice_and_plan_reminder() -> None:
    from realmock.domains.resume.agents.review import _vision_notice_message

    assert _vision_notice_message(locale="en", file_type="pdf", visual_status="ok") is None
    assert _vision_notice_message(locale="en", file_type="docx", visual_status="no_vision") is None
    assert _vision_notice_message(locale="en", file_type="pdf", visual_status="unknown") is None
    assert "Vision" in (_vision_notice_message(locale="en", file_type="pdf", visual_status="no_vision") or "")
    assert "纯文本" in (_vision_notice_message(locale="zh-CN", file_type="PDF", visual_status="missing_file") or "")


def test_restore_merge_attach_helpers() -> None:
    from realmock.domains.resume.agents.review import (
        _attach_review_audit,
        _merge_search_queries_used,
        _restore_max_tokens,
    )
    from realmock.domains.resume.agents.process import ReviewProcess

    class _LLM:
        max_tokens = 5

    llm = _LLM()
    _restore_max_tokens(llm, 9)  # type: ignore[arg-type]
    assert llm.max_tokens == 9

    class _BadLLM:
        @property
        def max_tokens(self):
            return 1

        @max_tokens.setter
        def max_tokens(self, value):
            raise RuntimeError("frozen")

    _restore_max_tokens(_BadLLM(), 3)  # type: ignore[arg-type]

    assert _merge_search_queries_used(["a"], ["a", "b"]) == ["a", "b"]
    assert _merge_search_queries_used("bad", ["q"]) == ["q"]
    assert _merge_search_queries_used([], ["q"]) == ["q"]

    proc = ReviewProcess()
    payload = _attach_review_audit({"score": 1}, ["q1"], proc)
    assert payload["search_queries_used"] == ["q1"]
    assert "_agent_steps" in payload


@pytest.mark.asyncio
async def test_build_tool_executor_plan_and_circuit(monkeypatch) -> None:
    from realmock.domains.resume.agents.review import _build_tool_executor

    seen = []

    class _Bundle:
        async def execute(self, name, args):
            seen.append(name)
            return '{"ok": true}', "ok"

    used: list[str] = []
    events: list[dict] = []
    ex = _build_tool_executor(_Bundle(), used, events.append)  # type: ignore[arg-type]
    out = await ex("review_set_plan", {"steps": ["a"]})
    assert "ok" in out
    assert used == ["review_set_plan"]
    assert events == []

    out2 = await ex("web_search", {"query": "q"})
    assert "ok" in out2
    assert any(e["type"] == "tool_step" for e in events)


def test_build_snapshot_and_bundle(db) -> None:
    from realmock.domains.resume.agents.review import build_resume_snapshot, build_review_bundle
    from realmock.domains.resume.agents.process import ReviewProcess

    row = _resume_row(parsed_profile='{"layout_notes": "two-col"}')
    row.id = 7
    snap = build_resume_snapshot(row)
    assert snap.resume_id == 7
    snap2 = build_resume_snapshot(_resume_row(parsed_profile="bad"))
    assert snap2.resume_id == 0

    queries: list[str] = []
    bundle = build_review_bundle(snapshot=snap, db=db, process=ReviewProcess(), search_queries=queries)
    names = {d["function"]["name"] for d in bundle.definitions()}
    assert "review_set_plan" in names
    assert "web_search" in names


@pytest.mark.asyncio
async def test_run_resume_review_success_and_reminder(monkeypatch, db) -> None:
    import realmock.domains.resume.agents.review as rev
    from realmock.platform.capabilities.ai.agent import LoopResult

    row = _resume_row()
    row.id = 11

    class _LLM:
        context_window = 8000
        max_tokens = 4000
        supports_vision = False
        api_key = "k"

    llm = _LLM()
    monkeypatch.setattr(rev, "_calibration_for_review", lambda resume, db: "")

    async def _fake_user_msg(*a, **k):
        return {"role": "user", "content": "overview"}

    monkeypatch.setattr(rev, "build_review_user_message", _fake_user_msg)
    monkeypatch.setattr(rev, "build_review_bundle", lambda **k: SimpleBundle())

    async def _boom_compact(*a, **k):
        raise RuntimeError("compact-boom")

    monkeypatch.setattr(rev, "compact_with_summary", _boom_compact)

    class SimpleBundle:
        def definitions(self):
            return []

    async def _fake_loop(llm_, messages, **kwargs):
        # exercise prepare_messages (compaction failure + plan reminder) twice
        prep = kwargs["prepare_messages"]
        kwargs.get("compact_observation")
        await kwargs["on_thinking"]("think-text")
        m1 = await prep([{"role": "user", "content": "u"}])
        m2 = await prep([{"role": "user", "content": "u"}])
        assert isinstance(m1, list) and isinstance(m2, list)
        assert any("review_set_plan" in str(m) for m in m2)
        obs = await kwargs["compact_observation"]("tool-text")
        assert obs is not None
        return LoopResult(messages=m1, final_content='{"score": 1}', tool_used=True)

    monkeypatch.setattr(rev, "run_agent_loop", _fake_loop)

    async def _fake_finalize(loop, llm_, locale, max_output, **kwargs):
        return {"score": 5}

    monkeypatch.setattr(rev, "finalize_review_json", _fake_finalize)
    events: list[dict] = []

    async def _on_event(e):
        events.append(e)

    out = await rev.run_resume_review(row, db, llm, locale="en", on_event=_on_event)  # type: ignore[arg-type]
    assert out["score"] == 5
    assert out["search_queries_used"] == []
    assert llm.max_tokens == 4000
    assert any(e.get("type") == "thinking" for e in events)


@pytest.mark.asyncio
async def test_run_resume_review_visual_notice_and_errors(monkeypatch, db) -> None:
    import realmock.domains.resume.agents.review as rev
    from realmock.platform.capabilities.ai.agent import LoopResult
    from realmock.platform.core.errors import ApiBusinessError

    row = _resume_row()
    row.id = 12

    class _LLM:
        context_window = 8000
        max_tokens = 4000
        supports_vision = False
        api_key = "k"

    # visual notice path (missing_file for pdf without vision? force via snapshot patch)
    monkeypatch.setattr(rev, "_calibration_for_review", lambda r, d: "")
    monkeypatch.setattr(rev, "build_resume_snapshot", lambda r, has_visual_pages=False: SimpleNamespace(file_type="pdf", visual_status="missing_file", raw_text="x", parsed={}, layout_notes="", filename="a.pdf", resume_id=1))

    async def _user_msg(*a, **k):
        return {"role": "user", "content": "u"}

    monkeypatch.setattr(rev, "build_review_user_message", _user_msg)
    monkeypatch.setattr(rev, "build_review_bundle", lambda **k: SimpleNamespace(definitions=lambda: []))

    async def _loop_ok(llm_, messages, **kwargs):
        return LoopResult(messages=[], final_content="{}", tool_used=False)

    monkeypatch.setattr(rev, "run_agent_loop", _loop_ok)

    async def _fake_fin(*a, **k):
        return {"score": 1}

    monkeypatch.setattr(rev, "finalize_review_json", _fake_fin)
    notices: list[dict] = []

    async def _on_event(e):
        notices.append(e)

    out = await rev.run_resume_review(row, db, _LLM(), locale="zh-CN", on_event=_on_event)  # type: ignore[arg-type]
    assert out["score"] == 1
    assert any(e.get("type") == "notice" for e in notices)

    # ApiBusinessError propagates and restores budget
    async def _loop_biz(*a, **k):
        from realmock.platform.core.errors import raise_error

        raise_error("A0006")

    monkeypatch.setattr(rev, "run_agent_loop", _loop_biz)
    llm2 = _LLM()
    with pytest.raises(ApiBusinessError) as exc:
        await rev.run_resume_review(row, db, llm2, locale="en")  # type: ignore[arg-type]
    assert exc.value.error_code == "A0006"
    assert llm2.max_tokens == 4000

    # generic exception becomes C0001
    async def _loop_boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(rev, "run_agent_loop", _loop_boom)
    with pytest.raises(ApiBusinessError) as exc2:
        await rev.run_resume_review(row, db, _LLM(), locale="en")  # type: ignore[arg-type]
    assert exc2.value.error_code == "C0001"


@pytest.mark.asyncio
async def test_forced_final_answer_branches() -> None:
    from realmock.domains.resume.agents.review import _request_forced_final_answer
    from realmock.platform.capabilities.ai.agent import LoopResult

    loop = LoopResult(
        messages=[{"role": "user", "content": "overview"}],
        final_content=None,
        tool_used=True,
    )

    seen: dict = {}

    class _LLM:
        async def chat(self, messages, **kwargs):
            seen["messages"] = messages
            seen["kwargs"] = kwargs
            return '{"score": 9}'

    out = await _request_forced_final_answer(_LLM(), loop, locale="en")  # type: ignore[arg-type]
    assert out == '{"score": 9}'
    # History is reused and the call offers no tools.
    assert seen["messages"][0] == {"role": "user", "content": "overview"}
    assert "Tools are now disabled" in seen["messages"][-1]["content"]
    assert "tools" not in seen["kwargs"]

    class _EmptyLLM:
        async def chat(self, *a, **k):
            return "  "

    assert await _request_forced_final_answer(_EmptyLLM(), loop, locale="en") is None  # type: ignore[arg-type]

    class _BoomLLM:
        async def chat(self, *a, **k):
            raise RuntimeError("llm-down")

    assert await _request_forced_final_answer(_BoomLLM(), loop, locale="en") is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_run_resume_review_forces_final_answer_on_exhaustion(monkeypatch, db) -> None:
    import realmock.domains.resume.agents.review as rev
    from realmock.platform.capabilities.ai.agent import LoopResult

    row = _resume_row()
    row.id = 13
    monkeypatch.setattr(rev, "_calibration_for_review", lambda r, d: "")

    async def _user_msg(*a, **k):
        return {"role": "user", "content": "u"}

    monkeypatch.setattr(rev, "build_review_user_message", _user_msg)
    monkeypatch.setattr(rev, "build_review_bundle", lambda **k: SimpleNamespace(definitions=lambda: []))

    async def _loop_exhausted(llm_, messages, **kwargs):
        return LoopResult(messages=[{"role": "user", "content": "u"}], final_content=None, tool_used=True)

    monkeypatch.setattr(rev, "run_agent_loop", _loop_exhausted)

    chat_calls: list = []

    class _LLM:
        context_window = 8000
        max_tokens = 4000
        supports_vision = False
        api_key = "k"

        async def chat(self, messages, **kwargs):
            chat_calls.append((messages, kwargs))
            return '{"score": 7}'

    captured: dict = {}

    async def _fake_finalize(loop, llm_, locale, max_output, **kwargs):
        captured["final_content"] = loop.final_content
        return {"score": 7}

    monkeypatch.setattr(rev, "finalize_review_json", _fake_finalize)

    out = await rev.run_resume_review(row, db, _LLM(), locale="en")  # type: ignore[arg-type]
    assert out["score"] == 7
    assert captured["final_content"] == '{"score": 7}'
    assert len(chat_calls) == 1


@pytest.mark.asyncio
async def test_run_resume_review_skips_forced_answer_without_tools(monkeypatch, db) -> None:
    import realmock.domains.resume.agents.review as rev
    from realmock.platform.capabilities.ai.agent import LoopResult

    row = _resume_row()
    row.id = 14
    monkeypatch.setattr(rev, "_calibration_for_review", lambda r, d: "")

    async def _user_msg(*a, **k):
        return {"role": "user", "content": "u"}

    monkeypatch.setattr(rev, "build_review_user_message", _user_msg)
    monkeypatch.setattr(rev, "build_review_bundle", lambda **k: SimpleNamespace(definitions=lambda: []))

    async def _loop_silent(llm_, messages, **kwargs):
        return LoopResult(messages=[], final_content=None, tool_used=False)

    monkeypatch.setattr(rev, "run_agent_loop", _loop_silent)

    class _LLM:
        context_window = 8000
        max_tokens = 4000
        supports_vision = False
        api_key = "k"

        async def chat(self, *a, **k):
            raise AssertionError("forced answer must not run without tool evidence")

    async def _fake_finalize(loop, llm_, locale, max_output, **kwargs):
        return {"score": 1}

    monkeypatch.setattr(rev, "finalize_review_json", _fake_finalize)

    out = await rev.run_resume_review(row, db, _LLM(), locale="en")  # type: ignore[arg-type]
    assert out["score"] == 1


@pytest.mark.asyncio
async def test_run_resume_review_soft_controls(monkeypatch, db) -> None:
    """The loop gets the tool-free final round, ladder window, and one retry."""
    import realmock.domains.resume.agents.review as rev
    from realmock.platform.capabilities.ai.agent import LoopResult

    class _Bundle:
        def definitions(self):
            return []

    row = _resume_row()
    row.id = 21

    class _LLM:
        context_window = 8000
        max_tokens = 4000
        supports_vision = False
        api_key = "k"

    llm = _LLM()
    monkeypatch.setattr(rev, "_calibration_for_review", lambda resume, db: "")

    async def _fake_user_msg(*a, **k):
        return {"role": "user", "content": "overview"}

    monkeypatch.setattr(rev, "build_review_user_message", _fake_user_msg)
    monkeypatch.setattr(rev, "build_review_bundle", lambda **k: _Bundle())

    captured: dict = {}

    async def _fake_loop(llm_, messages, **kwargs):
        captured.update(kwargs)
        return LoopResult(messages=messages, final_content='{"score": 3}', tool_used=False)

    monkeypatch.setattr(rev, "run_agent_loop", _fake_loop)

    async def _fake_finalize(loop, llm_, locale, max_output, **kwargs):
        return {"score": 3}

    monkeypatch.setattr(rev, "finalize_review_json", _fake_finalize)

    await rev.run_resume_review(row, db, llm, locale="en")  # type: ignore[arg-type]
    assert "deadline" not in captured, "no wall-clock budget may reach the loop"
    assert captured["final_round_tool_free"] is True
    assert captured["countdown_rounds"] == rev.REVIEW_COUNTDOWN_ROUNDS
    assert captured["round_retries"] == 1


@pytest.mark.asyncio
async def test_run_resume_review_progress_line_is_transient_suffix(monkeypatch, db) -> None:
    """The budget line is appended at the end, never prepended (prefix cache)."""
    import realmock.domains.resume.agents.review as rev
    from realmock.platform.capabilities.ai.agent import LoopResult

    class _Bundle:
        def definitions(self):
            return []

    row = _resume_row()
    row.id = 22

    class _LLM:
        context_window = 8000
        max_tokens = 4000
        supports_vision = False
        api_key = "k"

    llm = _LLM()
    monkeypatch.setattr(rev, "_calibration_for_review", lambda resume, db: "")

    async def _fake_user_msg(*a, **k):
        return {"role": "user", "content": "overview"}

    monkeypatch.setattr(rev, "build_review_user_message", _fake_user_msg)
    monkeypatch.setattr(rev, "build_review_bundle", lambda **k: _Bundle())

    last_call: list = []

    async def _fake_loop(llm_, messages, **kwargs):
        prepared = await kwargs["prepare_messages"]([{"role": "user", "content": "u"}])
        last_call.append(prepared)
        assert prepared[-1]["role"] == "system"
        assert "Progress: LLM round 1/" in prepared[-1]["content"]
        assert all("Progress: LLM round" not in str(m) for m in prepared[:-1])
        return LoopResult(messages=prepared, final_content='{"score": 4}', tool_used=False)

    monkeypatch.setattr(rev, "run_agent_loop", _fake_loop)

    async def _fake_finalize(loop, llm_, locale, max_output, **kwargs):
        return {"score": 4}

    monkeypatch.setattr(rev, "finalize_review_json", _fake_finalize)

    await rev.run_resume_review(row, db, llm, locale="en")  # type: ignore[arg-type]
    assert last_call


@pytest.mark.asyncio
async def test_finalize_self_correction_recovers() -> None:
    """A malformed draft is fixed by one self-correction round, not repair."""
    from realmock.domains.resume.agents.review import finalize_review_json
    from realmock.platform.capabilities.ai.agent import LoopResult

    class _LLM:
        async def chat(self, messages, **k):
            # The draft rides along as an assistant message before the ask.
            assert any(m.get("role") == "assistant" and "prose" in str(m.get("content")) for m in messages)
            return '{"score": 8, "dimension_scores": {}}'

        async def chat_json(self, *a, **k):
            raise AssertionError("repair must not run when self-correction succeeds")

    loop = LoopResult(
        messages=[{"role": "user", "content": "overview"}],
        final_content="some prose {broken json",
        tool_used=True,
    )
    out = await finalize_review_json(loop, _LLM(), locale="en", max_output=512)  # type: ignore[arg-type]
    assert out["score"] == 8


@pytest.mark.asyncio
async def test_finalize_self_correction_failure_falls_to_repair() -> None:
    """When the correction round also fails to parse, repair still runs."""
    from realmock.domains.resume.agents.review import finalize_review_json
    from realmock.platform.capabilities.ai.agent import LoopResult

    class _LLM:
        async def chat(self, messages, **k):
            return "still not json"

        async def chat_json(self, messages, **k):
            return {"score": 9}

    loop = LoopResult(
        messages=[{"role": "user", "content": "overview"}],
        final_content="prose {broken",
        tool_used=True,
    )
    out = await finalize_review_json(loop, _LLM(), locale="en", max_output=512)  # type: ignore[arg-type]
    assert out == {"score": 9}


@pytest.mark.asyncio
async def test_finalize_self_correction_is_bounded(monkeypatch) -> None:
    """A hung self-correction round is cut off and the chain falls through to repair.

    Without the outer bound this phase could consume the rest of the frontend
    budget on a flaky network and the whole run would deliver nothing.
    """
    import asyncio

    import realmock.domains.resume.agents.review as rev
    from realmock.platform.capabilities.ai.agent import LoopResult

    class _HangLLM:
        async def chat(self, messages, **k):
            del messages, k
            await asyncio.sleep(5.0)
            return "late"  # pragma: no cover

        async def chat_json(self, messages, **k):
            del messages, k
            return {"score": 6}

    monkeypatch.setattr(rev, "REVIEW_SELF_CORRECTION_TIMEOUT_SECONDS", 0.05)
    loop = LoopResult(
        messages=[{"role": "user", "content": "overview"}],
        final_content="prose {broken",
        tool_used=True,
    )
    out = await rev.finalize_review_json(loop, _HangLLM(), locale="en", max_output=512)  # type: ignore[arg-type]
    assert out == {"score": 6}


@pytest.mark.asyncio
async def test_finalize_skips_self_correction_on_empty_draft() -> None:
    """No draft means nothing to self-correct; repair handles it directly."""
    from realmock.domains.resume.agents.review import finalize_review_json
    from realmock.platform.capabilities.ai.agent import LoopResult

    class _LLM:
        async def chat(self, *a, **k):
            raise AssertionError("self-correction must not run on an empty draft")

        async def chat_json(self, messages, **k):
            return {"score": 6}

    loop = LoopResult(
        messages=[{"role": "user", "content": "overview"}],
        final_content="",
        tool_used=True,
    )
    out = await finalize_review_json(loop, _LLM(), locale="en", max_output=512)  # type: ignore[arg-type]
    assert out == {"score": 6}


@pytest.mark.asyncio
async def test_build_tool_executor_budget_and_args_keyed_breaker(monkeypatch) -> None:
    """Total budget refuses without executing; the breaker keys on tool+args."""

    async def _fake_invoke(bundle, name, args, context=None):
        if name == "web_search":
            return '{"hits": 1}', "done"
        return '{"error": "timeout"}', "error"

    import realmock.domains.resume.agents.review as rev

    monkeypatch.setattr(rev, "_invoke_review_tool", _fake_invoke)

    used: list[str] = []
    budget = {"tool_calls": 0}
    activity: list[str] = []
    ex = rev._build_tool_executor(
        object(), used, None, None, budget, activity_sink=activity.append  # type: ignore[arg-type]
    )

    # Same call failing three times in a row arms the breaker...
    for _ in range(3):
        out = await ex("github_get_readme", {"repo": "a/b"})
        assert "timeout" in out
    blocked = await ex("github_get_readme", {"repo": "a/b"})
    assert '"circuit_open"' in blocked
    # ...but different arguments are a different workload: allowed.
    ok = await ex("github_get_readme", {"repo": "c/d"})
    assert "timeout" in ok, "different arguments must not be blocked"

    # Budget refusal: no execution once the ceiling is reached.
    budget["tool_calls"] = rev.REVIEW_MAX_TOTAL_TOOL_CALLS
    refused = await ex("web_search", {"query": "fresh"})
    assert '"tool_budget_exhausted"' in refused
    assert used[-1] == "web_search"

    # Executed calls (success or error) feed the step-note activity sink;
    # blocked calls do not.
    assert activity == [
        "github_get_readme(a/b)",
        "github_get_readme(a/b)",
        "github_get_readme(a/b)",
        "github_get_readme(c/d)",
    ]


@pytest.mark.asyncio
async def test_build_tool_executor_budget_slot_reservation(monkeypatch) -> None:
    """The budget slot is reserved before the first await point.

    Concurrent calls in one parallel round all pass the same gate check, so a
    check-then-increment-after-execution scheme lets them jointly overshoot
    the soft ceiling; circuit-open refusals refund their reserved slot.
    """

    async def _fake_invoke(bundle, name, args, context=None):
        # The real invoker always suspends (asyncio.wait_for around the tool
        # call); sleep(0) reproduces that yield so the parallel burst below
        # actually interleaves instead of running sequentially.
        await asyncio.sleep(0)
        return '{"error": "timeout"}', "error"

    import realmock.domains.resume.agents.review as rev

    monkeypatch.setattr(rev, "_invoke_review_tool", _fake_invoke)

    budget = {"tool_calls": 0}
    ex = rev._build_tool_executor(object(), [], None, None, budget)  # type: ignore[arg-type]

    for _ in range(3):
        await ex("github_get_readme", {"repo": "a/b"})
    assert budget["tool_calls"] == 3
    blocked = await ex("github_get_readme", {"repo": "a/b"})
    assert '"circuit_open"' in blocked
    assert budget["tool_calls"] == 3, "circuit-open refusal must refund the slot"

    # One slot left: a parallel burst executes exactly one call, the rest are
    # refused at the gate, and the ceiling ends up exact.
    budget["tool_calls"] = rev.REVIEW_MAX_TOTAL_TOOL_CALLS - 1
    outs = await asyncio.gather(
        ex("web_search", {"query": "q1"}),
        ex("web_search", {"query": "q2"}),
        ex("web_search", {"query": "q3"}),
    )
    executed = [o for o in outs if "tool_budget_exhausted" not in o]
    refused = [o for o in outs if "tool_budget_exhausted" in o]
    assert len(executed) == 1
    assert len(refused) == 2
    assert budget["tool_calls"] == rev.REVIEW_MAX_TOTAL_TOOL_CALLS


@pytest.mark.asyncio
async def test_run_resume_review_plan_complete_nudge(monkeypatch, db) -> None:
    """Once every plan step is done, rounds get a strong finalize instruction."""
    import realmock.domains.resume.agents.review as rev
    from realmock.platform.capabilities.ai.agent import LoopResult

    row = _resume_row()
    row.id = 23

    class _LLM:
        context_window = 8000
        max_tokens = 4000
        supports_vision = False
        api_key = "k"

    llm = _LLM()
    monkeypatch.setattr(rev, "_calibration_for_review", lambda resume, db: "")

    async def _fake_user_msg(*a, **k):
        return {"role": "user", "content": "overview"}

    monkeypatch.setattr(rev, "build_review_user_message", _fake_user_msg)

    nudge = "All plan steps are complete"

    async def _fake_loop(llm_, messages, **kwargs):
        execute = kwargs["execute"]
        await execute(
            "review_set_plan",
            {"steps": [f"step {i}" for i in range(1, 8)] + ["Generate evaluation JSON"]},
        )
        prepared = await kwargs["prepare_messages"]([{"role": "user", "content": "u"}])
        assert not any(nudge in str(m.get("content")) for m in prepared)
        for index in range(1, 9):
            await execute("review_update_step", {"id": str(index), "status": "done"})
        prepared_done = await kwargs["prepare_messages"]([{"role": "user", "content": "u"}])
        assert any(nudge in str(m.get("content")) for m in prepared_done)
        return LoopResult(messages=prepared_done, final_content='{"score": 2}', tool_used=True)

    monkeypatch.setattr(rev, "run_agent_loop", _fake_loop)

    async def _fake_finalize(loop, llm_, locale, max_output, **kwargs):
        return {"score": 2}

    monkeypatch.setattr(rev, "finalize_review_json", _fake_finalize)

    out = await rev.run_resume_review(row, db, llm, locale="en")  # type: ignore[arg-type]
    assert out["score"] == 2


@pytest.mark.asyncio
async def test_run_resume_review_forced_final_is_bounded(monkeypatch, db) -> None:
    """A hung forced-final call times out and the run still reaches finalize."""
    import asyncio

    import realmock.domains.resume.agents.review as rev
    from realmock.platform.capabilities.ai.agent import LoopResult

    class _Bundle:
        def definitions(self):
            return []

    row = _resume_row()
    row.id = 24

    class _HangLLM:
        context_window = 8000
        max_tokens = 4000
        supports_vision = False
        api_key = "k"

        async def chat(self, messages, **k):
            del messages, k
            await asyncio.sleep(5.0)
            return "late"  # pragma: no cover

    llm = _HangLLM()
    monkeypatch.setattr(rev, "_calibration_for_review", lambda resume, db: "")

    async def _fake_user_msg(*a, **k):
        return {"role": "user", "content": "overview"}

    monkeypatch.setattr(rev, "build_review_user_message", _fake_user_msg)
    monkeypatch.setattr(rev, "build_review_bundle", lambda **k: _Bundle())
    monkeypatch.setattr(rev, "REVIEW_FORCED_FINAL_TIMEOUT_SECONDS", 0.05)

    async def _fake_loop(llm_, messages, **kwargs):
        return LoopResult(messages=messages, final_content=None, tool_used=True)

    monkeypatch.setattr(rev, "run_agent_loop", _fake_loop)

    finalize_called: list = []

    async def _fake_finalize(loop, llm_, locale, max_output, **kwargs):
        finalize_called.append(loop)
        return {"score": 1}

    monkeypatch.setattr(rev, "finalize_review_json", _fake_finalize)

    out = await rev.run_resume_review(row, db, llm, locale="en")  # type: ignore[arg-type]
    assert out["score"] == 1
    assert finalize_called and finalize_called[0].final_content is None, (
        "the hung forced-final must not feed a partial answer into finalize"
    )
    assert llm.max_tokens == 4000, "client budget restored even on the timeout path"


@pytest.mark.asyncio
async def test_finalize_emits_progress_notices() -> None:
    """Self-correction and repair announce themselves on the event stream."""
    from realmock.domains.resume.agents.review import finalize_review_json
    from realmock.platform.capabilities.ai.agent import LoopResult

    events: list[dict] = []

    async def _on_event(event):
        events.append(event)

    class _LLM:
        async def chat(self, messages, **k):
            del messages, k
            return "still not json"

        async def chat_json(self, messages, **k):
            del messages, k
            return {"score": 5}

    loop = LoopResult(
        messages=[{"role": "user", "content": "overview"}],
        final_content="prose {broken",
        tool_used=True,
    )
    out = await finalize_review_json(
        loop, _LLM(), locale="zh-CN", max_output=512, on_event=_on_event  # type: ignore[arg-type]
    )
    assert out == {"score": 5}
    kinds = [str(e.get("message")) for e in events if e.get("type") == "notice"]
    assert any("重新输出" in m for m in kinds)
    assert any("重建评价 JSON" in m for m in kinds)


@pytest.mark.asyncio
async def test_run_resume_review_progress_line_counts_executed_tools(monkeypatch, db) -> None:
    """The budget line tracks executed non-plan calls, and the create-plan nudge
    coexists with it as transient suffixes of the same round."""
    import realmock.domains.resume.agents.review as rev
    from realmock.platform.capabilities.ai.agent import LoopResult

    class _StubBundle:
        def definitions(self):
            return []

        async def execute(self, name, args):
            return '{"ok": true}'

    row = _resume_row()
    row.id = 26

    class _LLM:
        context_window = 8000
        max_tokens = 4000
        supports_vision = False
        api_key = "k"

    llm = _LLM()
    monkeypatch.setattr(rev, "_calibration_for_review", lambda resume, db: "")

    async def _fake_user_msg(*a, **k):
        return {"role": "user", "content": "overview"}

    monkeypatch.setattr(rev, "build_review_user_message", _fake_user_msg)
    monkeypatch.setattr(rev, "build_review_bundle", lambda **k: _StubBundle())

    async def _fake_loop(llm_, messages, **kwargs):
        prepare = kwargs["prepare_messages"]
        execute = kwargs["execute"]
        first = await prepare([{"role": "user", "content": "u"}])
        assert "Tool calls used: 0/" in str(first[-1]["content"])
        await execute("review_get_plan", {})  # plan bookkeeping: no budget cost
        for _ in range(3):
            await execute("resume_overview", {})
        second = await prepare([{"role": "user", "content": "u"}])
        assert "LLM round 2/" in str(second[-1]["content"])
        assert "Tool calls used: 3/" in str(second[-1]["content"])
        # 催收提示与预算行同轮共存：plan reminder (suffix -2) + progress line (suffix -1)
        assert "Create the review plan" in str(second[-2].get("content"))
        return LoopResult(messages=second, final_content='{"score": 5}', tool_used=True)

    monkeypatch.setattr(rev, "run_agent_loop", _fake_loop)

    async def _fake_finalize(loop, llm_, locale, max_output, **kwargs):
        return {"score": 5}

    monkeypatch.setattr(rev, "finalize_review_json", _fake_finalize)

    out = await rev.run_resume_review(row, db, llm, locale="en")  # type: ignore[arg-type]
    assert out["score"] == 5


@pytest.mark.asyncio
async def test_run_resume_review_plan_reminder_is_capped(monkeypatch, db) -> None:
    """Without a declared plan, the create-plan nudge repeats at most three times."""
    import realmock.domains.resume.agents.review as rev
    from realmock.platform.capabilities.ai.agent import LoopResult

    row = _resume_row()
    row.id = 27

    class _LLM:
        context_window = 8000
        max_tokens = 4000
        supports_vision = False
        api_key = "k"

    llm = _LLM()
    monkeypatch.setattr(rev, "_calibration_for_review", lambda resume, db: "")

    async def _fake_user_msg(*a, **k):
        return {"role": "user", "content": "overview"}

    monkeypatch.setattr(rev, "build_review_user_message", _fake_user_msg)

    async def _fake_loop(llm_, messages, **kwargs):
        prepare = kwargs["prepare_messages"]
        reminders = 0
        for _ in range(5):
            prepared = await prepare([{"role": "user", "content": "u"}])
            if any(
                "Create the review plan" in str(m.get("content")) for m in prepared
            ):
                reminders += 1
        assert reminders == 3, "the nudge must stop after three rounds, not nag forever"
        return LoopResult(messages=prepared, final_content='{"score": 7}', tool_used=True)

    monkeypatch.setattr(rev, "run_agent_loop", _fake_loop)

    async def _fake_finalize(loop, llm_, locale, max_output, **kwargs):
        return {"score": 7}

    monkeypatch.setattr(rev, "finalize_review_json", _fake_finalize)

    out = await rev.run_resume_review(row, db, llm, locale="en")  # type: ignore[arg-type]
    assert out["score"] == 7


@pytest.mark.asyncio
async def test_prepare_messages_retires_images_by_round_ratio_without_layout_step(
    monkeypatch, db
) -> None:
    """Fallback retirement: no plan step owns the layout review, so the page
    images still stop being re-sent once two thirds of the rounds are spent."""
    import realmock.domains.resume.agents.review as rev
    from realmock.platform.capabilities.ai.agent import LoopResult

    # 15 rounds -> threshold max(8, int(15 * 2/3)) = 10: retire at round 10.
    monkeypatch.setattr(rev, "REVIEW_MAX_ROUNDS", 15)

    image_part = {"type": "image_url", "image_url": {"url": "data:image/png;base64,x"}}
    multimodal = {
        "role": "user",
        "content": [{"type": "text", "text": "overview"}, image_part],
    }

    row = _resume_row()
    row.id = 28

    class _LLM:
        context_window = 8000
        max_tokens = 4000
        supports_vision = True
        api_key = "k"

    llm = _LLM()
    monkeypatch.setattr(rev, "_calibration_for_review", lambda resume, db: "")

    async def _fake_user_msg(*a, **k):
        return multimodal

    monkeypatch.setattr(rev, "build_review_user_message", _fake_user_msg)

    async def _fake_loop(llm_, messages, **kwargs):
        prepare = kwargs["prepare_messages"]
        images_by_round: list[bool] = []
        for _ in range(10):
            prepared = await prepare([multimodal])
            first_user = next(m for m in prepared if m.get("role") == "user")
            images_by_round.append(
                any(
                    isinstance(part, dict) and part.get("type") == "image_url"
                    for part in first_user["content"]
                )
            )
        assert all(images_by_round[:9]), "images stay attached through round 9"
        assert not images_by_round[9], "the ratio bound retires them at round 10"
        assert any(
            "page images" in str(part.get("text")) for part in first_user["content"]
        ), "retirement replaces images with an explicit text marker"
        return LoopResult(messages=prepared, final_content='{"score": 8}', tool_used=False)

    monkeypatch.setattr(rev, "run_agent_loop", _fake_loop)

    async def _fake_finalize(loop, llm_, locale, max_output, **kwargs):
        return {"score": 8}

    monkeypatch.setattr(rev, "finalize_review_json", _fake_finalize)

    out = await rev.run_resume_review(row, db, llm, locale="en")  # type: ignore[arg-type]
    assert out["score"] == 8


@pytest.mark.asyncio
async def test_prepare_messages_retires_images_after_layout_step(monkeypatch, db) -> None:
    """Once the layout step is done, page images are replaced by a marker."""
    import realmock.domains.resume.agents.review as rev
    from realmock.platform.capabilities.ai.agent import LoopResult

    image_part = {"type": "image_url", "image_url": {"url": "data:image/png;base64,x"}}
    multimodal = {
        "role": "user",
        "content": [{"type": "text", "text": "overview"}, image_part],
    }

    row = _resume_row()
    row.id = 25

    class _LLM:
        context_window = 8000
        max_tokens = 4000
        supports_vision = True
        api_key = "k"

    llm = _LLM()
    monkeypatch.setattr(rev, "_calibration_for_review", lambda resume, db: "")

    async def _fake_user_msg(*a, **k):
        return multimodal

    monkeypatch.setattr(rev, "build_review_user_message", _fake_user_msg)

    async def _fake_loop(llm_, messages, **kwargs):
        execute = kwargs["execute"]
        await execute(
            "review_set_plan",
            {"steps": ["step a", "从页面图像评审版式与排版", "step c", "step d",
                       "step e", "step f", "step g", "Generate evaluation JSON"]},
        )
        before = await kwargs["prepare_messages"]([multimodal])
        first_before = next(m for m in before if m.get("role") == "user")
        assert any(
            isinstance(part, dict) and part.get("type") == "image_url"
            for part in first_before["content"]
        ), "images must stay attached while the layout step is open"
        await execute("review_update_step", {"id": "2", "status": "done"})
        after = await kwargs["prepare_messages"]([multimodal])
        first_after = next(m for m in after if m.get("role") == "user")
        assert not any(
            isinstance(part, dict) and part.get("type") == "image_url"
            for part in first_after["content"]
        )
        assert any("page images" in str(part.get("text")) for part in first_after["content"])
        return LoopResult(messages=after, final_content='{"score": 6}', tool_used=False)

    monkeypatch.setattr(rev, "run_agent_loop", _fake_loop)

    async def _fake_finalize(loop, llm_, locale, max_output, **kwargs):
        return {"score": 6}

    monkeypatch.setattr(rev, "finalize_review_json", _fake_finalize)

    out = await rev.run_resume_review(row, db, llm, locale="en")  # type: ignore[arg-type]
    assert out["score"] == 6
