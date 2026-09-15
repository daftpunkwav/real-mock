"""Review agent tests for src/realmock/domains/resume/agents/review.py.

Covers: _parsed_dict/_query_from_args/_content_as_text/evidence_for_repair/
finalize_review_json/_reinsert_first_user/_vision_notice_message/
_restore_max_tokens/_merge_search_queries_used/_attach_review_audit/
_build_tool_executor/build_resume_snapshot/build_review_bundle/run_resume_review
success/reminder/notice/error branches (LLM/loop mocked).
Conventions: no real network/model downloads (all clients mocked); faked LLM/DB;
rate limits reset per test.
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
    import realmock.domains.resume.agents.review as rev

    async def _boom_blob(llm, text, purpose=""):
        return "evidence"

    monkeypatch.setattr(rev, "compress_text_blob", _boom_blob)

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

    async def _fake_compress(llm_, text, purpose=""):
        return "compressed"

    monkeypatch.setattr(rev, "compress_text_blob", _fake_compress)

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

    async def _fake_compress2(llm_, text, purpose=""):
        return "c"

    monkeypatch.setattr(rev, "compress_text_blob", _fake_compress2)

    async def _fake_finalize(loop, llm_, locale, max_output):
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
