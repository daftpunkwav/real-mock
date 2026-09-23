"""Context compression unit test."""

from __future__ import annotations

import pytest

from realmock.platform.capabilities.ai.agent.working_memory import WorkingMemory
from realmock.platform.capabilities.ai.context.manager import (
    compact_with_summary,
    compress_messages,
    estimate_messages_tokens,
    estimate_tokens,
)


def test_estimate_tokens_empty() -> None:
    assert estimate_tokens("") == 0


def test_estimate_tokens_rough_ratio() -> None:
    # Script-aware heuristic: Latin ~4 chars/token, CJK ~1.5 chars/token.
    assert estimate_tokens("abc") == 1  # floor of 1 token minimum
    assert estimate_tokens("Hello") == 1  # 5 / 4 = 1
    assert estimate_tokens("你好世界") == 2  # 4 / 1.5 = 2
    assert estimate_tokens("Hello你好") == 2  # 5 / 4 + 2 / 1.5 = 2


def test_compress_under_threshold_returns_input() -> None:
    msgs = [{"role": "user", "content": "Short message"}]
    out = compress_messages(msgs, max_tokens=10000)
    assert out is msgs or out == msgs


def test_compress_keeps_all_system_messages() -> None:
    msgs = [
        {"role": "system", "content": "Rule one"},
        {"role": "system", "content": "Rule two"},
    ] + [{"role": "user", "content": f"Message{i}"} for i in range(50)]
    out = compress_messages(msgs, max_tokens=100)
    system = [m for m in out if m["role"] == "system"]
    # Contains 2 original system messages + 1 compression note
    rule_msgs = [m for m in system if m["content"] in ("Rule one", "Rule two")]
    assert len(rule_msgs) == 2
    # The most recent 20 conversation messages should be retained
    assert any("Message49" in m["content"] for m in out)


def test_compress_adds_summary_marker() -> None:
    msgs = (
        [{"role": "system", "content": "Rules"}]
        + [{"role": "user", "content": f"old{i}"} for i in range(30)]
        + [{"role": "user", "content": f"new{i}"} for i in range(5)]
    )
    out = compress_messages(msgs, max_tokens=100)
    summary = [m for m in out if m["role"] == "system" and "Context compression" in m["content"]]
    assert summary


def test_estimate_messages_tokens_sums_contents() -> None:
    msgs = [
        {"role": "system", "content": "abc"},
        {"role": "user", "content": "defg"},
    ]
    # Latin 3/4 -> 1 and 4/4 -> 1, plus per-message framing overhead each.
    from realmock.platform.capabilities.ai.context.estimation import MESSAGE_OVERHEAD_TOKENS

    assert estimate_messages_tokens(msgs) == 1 + MESSAGE_OVERHEAD_TOKENS + 1 + MESSAGE_OVERHEAD_TOKENS


def test_compress_triggers_at_30_percent_threshold() -> None:
    """The trigger threshold has been lowered from 60% to 30%, so compression occurs even when total message tokens < max_tokens*0.6."""
    # Construct five user messages of about 187 tokens each → ~935 tokens total.
    big = "contentcontentcontentcontentcontentcontentcontentcontent" * 5  # "content" x8=56 chars x5=280 chars ~=186 tokens
    msgs = [{"role": "user", "content": big + str(i)} for i in range(5)]
    total = sum(estimate_messages_tokens([m]) for m in msgs)
    # Set max_tokens so the ratio falls within the (30%, 60%) range:
    # 30% * max_tokens < total < 60% * max_tokens
    max_tokens = int(total / 0.45)  # ~exactly a 45% share
    out = compress_messages(msgs, max_tokens=max_tokens)
    # Starting with five user messages, compression should leave fewer than five and add a system summary.
    system_marker = [m for m in out if m["role"] == "system" and "Context compression" in m["content"]]
    assert system_marker, "Compression should also trigger at the 30% threshold"


def test_estimate_messages_tokens_handles_list_content() -> None:
    """Accumulate correctly when multimodal content is list[dict, ...]."""
    msgs = [
        {"role": "user", "content": [{"type": "text", "text": "hello world"}]},
        {"role": "user", "content": "Short"},
    ]
    # "hello world" 11 chars => ~7 tokens; "Short" 5 chars => 3 tokens => about 10 total
    assert estimate_messages_tokens(msgs) >= 5


def test_estimate_messages_tokens_skips_empty_content() -> None:
    msgs = [
        {"role": "user", "content": ""},
        {"role": "assistant", "content": None},
    ]
    # Empty / None content should not raise an exception
    total = estimate_messages_tokens(msgs)
    assert total >= 0

# ── Folding old tool pairs ────────────────────────────────────────────────


def _turn_with_tools(user_text: str, tool_result: str, answer: str) -> list[dict]:
    """Construct one round of messages: user → tool call → tool result → answer."""
    return [
        {"role": "user", "content": user_text},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "web_search", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": tool_result},
        {"role": "assistant", "content": answer},
    ]


def test_compress_prunes_stale_tool_pairs() -> None:
    """Fold tool-call pairs before the most recent user message while keeping the final round's pairing intact."""
    big = "Observation" * 2000  # A single tool result is large
    msgs = (
        [{"role": "system", "content": "Rules"}]
        + _turn_with_tools("Previous question", big, "Previous answer" + "Supplement" * 1000)
        + [{"role": "user", "content": "Latest question"}]
    )
    out = compress_messages(msgs, max_tokens=10000)  # Threshold reached without omission
    roles = [m["role"] for m in out]
    assert "tool" not in roles, "Old tool results should be collapsed"
    assert not any(m.get("tool_calls") for m in out), "The old tool_calls structure should be removed"
    assert any(m["role"] == "assistant" and m.get("content", "").startswith("Previous answer") for m in out)
    # If present, the latest round (the current tool pair) must be preserved verbatim—the last message here is user, so this does not apply.


def test_compress_keeps_current_turn_tool_pairs() -> None:
    """The tool_calls/tool pairing in the current round (after the last user message) must remain intact."""
    big = "Content" * 3000
    msgs = (
        [{"role": "system", "content": "Rules"}]
        + [{"role": "user", "content": "Previous question" + big}]
        + [{"role": "assistant", "content": "Previous answer" + big}]
        + _turn_with_tools("Latest question", "Tool result", "Latest answer")
    )
    out = compress_messages(msgs, max_tokens=500, keep_recent=20)
    tail_user = max(i for i, m in enumerate(out) if m["role"] == "user")
    current = out[tail_user:]
    assert any(m.get("role") == "tool" for m in current), "The current turn's tool result must be retained"
    assert any(m.get("tool_calls") for m in current), "The current turn's tool_calls must be retained"


# ── LLM summary compression ──────────────────────────────────────────────


class _SummarizerLLM:
    """Programmable LLM for compression: chat returns a fixed summary or raises an error; record each call."""

    def __init__(self, reply: str = "", error: Exception | None = None):
        self.reply = reply
        self.error = error
        self.chat_calls: list[list[dict]] = []

    async def chat(self, messages, temperature=0.7, **kwargs):
        del temperature, kwargs
        self.chat_calls.append(messages)
        if self.error is not None:
            raise self.error
        return self.reply


def _big_history(turns: int = 12) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": "Rules"}]
    for i in range(turns):
        msgs.append({"role": "user", "content": f"Question{i}:" + "Context" * 300})
        msgs.append({"role": "assistant", "content": f"answer{i}:" + "Conclusion" * 300})
    return msgs


@pytest.mark.asyncio
async def test_compact_with_summary_under_threshold_skips_llm() -> None:
    llm = _SummarizerLLM(reply="Notes")
    msgs = [{"role": "user", "content": "Short question"}]
    out = await compact_with_summary(msgs, 100000, llm=llm)
    assert out == msgs
    assert llm.chat_calls == []


@pytest.mark.asyncio
async def test_compact_with_summary_generates_structured_summary() -> None:
    llm = _SummarizerLLM(reply="Session goal: analyze the resume\nTo do: simulate follow-up questions")
    mem = WorkingMemory()
    out = await compact_with_summary(_big_history(), 500, memory=mem, llm=llm, keep_recent=4)
    summaries = [
        m for m in out
        if m["role"] == "system" and str(m.get("content", "")).startswith("[Conversation Minutes]")
    ]
    assert len(summaries) == 1
    assert "Session goal" in summaries[0]["content"]
    # Omitted earlier conversation messages should no longer exist verbatim; retain the recent window
    assert not any(m["role"] == "user" and str(m.get("content", "")).startswith("Question0") for m in out)
    assert any(m["role"] == "user" and str(m.get("content", "")).startswith("Question11") for m in out)
    assert mem.notes, "Omitted conversation messages should also be incorporated into working memory"
    assert llm.chat_calls, "The LLM must be called to generate a summary when the threshold is exceeded"


@pytest.mark.asyncio
async def test_compact_with_summary_falls_back_to_digest_on_llm_failure() -> None:
    llm = _SummarizerLLM(error=RuntimeError("llm down"))
    out = await compact_with_summary(_big_history(), 500, llm=llm, keep_recent=4)
    digests = [
        m for m in out
        if m["role"] == "system" and str(m.get("content", "")).startswith("[Context compression]")
    ]
    assert digests, "LLM failure must fall back to a rule-based summary"


@pytest.mark.asyncio
async def test_compact_with_summary_supersedes_previous_summary() -> None:
    old = _big_history()
    old.insert(1, {"role": "system", "content": "[Session summary] Previous summary content"})
    llm = _SummarizerLLM(reply="New notes")
    out = await compact_with_summary(old, 500, llm=llm, keep_recent=4)
    summaries = [
        m for m in out
        if m["role"] == "system" and str(m.get("content", "")).startswith("[Conversation Minutes]")
    ]
    assert len(summaries) == 1
    assert "Previous summary content" not in summaries[0]["content"]
    # The previous summary should be passed to the LLM as input for an incremental update
    prompt = llm.chat_calls[0][0]["content"]
    assert "Previous summary content" in prompt


def test_compress_digest_includes_omitted_user_text() -> None:
    msgs = (
        [{"role": "system", "content": "Rules"}]
        + [{"role": "user", "content": f"old-topic-{i}"} for i in range(30)]
        + [{"role": "user", "content": "new-topic"}]
    )
    mem = WorkingMemory()
    out = compress_messages(msgs, max_tokens=80, memory=mem)
    summary = [m for m in out if m["role"] == "system" and "Context compression" in m["content"]]
    assert summary
    assert "old-topic-0" in summary[0]["content"]
    assert mem.notes


# ── Auto-gate default + cooldown ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compact_default_threshold_is_late_not_eager() -> None:
    """Agent-decided default fires on real pressure (≈80%), not early occupancy."""
    from realmock.platform.capabilities.ai.context.options import DEFAULT_AUTO_COMPACT_THRESHOLD

    assert DEFAULT_AUTO_COMPACT_THRESHOLD == 0.8
    big = "contentcontentcontentcontentcontentcontentcontentcontent" * 5
    msgs = [{"role": "user", "content": big + str(i)} for i in range(5)]
    total = sum(estimate_messages_tokens([m]) for m in msgs)
    llm = _SummarizerLLM(reply="Notes")
    out = await compact_with_summary(
        msgs, int(total / 0.45), llm=llm, keep_recent=2,
        threshold=DEFAULT_AUTO_COMPACT_THRESHOLD,
    )
    assert llm.chat_calls == [], "45% occupancy must not compact at the auto default"
    assert out == msgs


@pytest.mark.asyncio
async def test_compact_cooldown_skips_fresh_summaries() -> None:
    """A summary written last turn plus a barely grown history is left alone."""
    llm = _SummarizerLLM(reply="Notes")
    first = await compact_with_summary(
        _padded_history(turns=4), 100000, llm=llm, keep_recent=2, force=True
    )
    assert llm.chat_calls
    calls = len(llm.chat_calls)
    # NOTE: append turns only (a fresh system seed would interleave mid-list,
    # while the pipeline canonically returns system blocks first).
    grown = first + _turns_only(_padded_history(turns=1))
    # Size the window from the measured total: 50% occupancy passes the gate
    # but never trips urgency — only the cooldown may stop this run.
    max_tokens = int(estimate_messages_tokens(grown) / 0.5)
    out = await compact_with_summary(grown, max_tokens, llm=llm, keep_recent=2)
    assert out == grown, "2 fresh messages must not trigger a rewrite"
    assert len(llm.chat_calls) == calls, "cooldown must save the summarizer call"


def _turns_only(messages: list[dict]) -> list[dict]:
    """Append turns without reseeding system blocks (keeps canonical order)."""
    return [m for m in messages if m.get("role") != "system"]


def _padded_history(turns: int) -> list[dict]:
    """Realistic-size turns: tiny fixtures would never clear the fold floor."""
    msgs: list[dict] = [{"role": "system", "content": "Rules"}]
    pad = " Body" * 200
    for i in range(turns):
        msgs.append({"role": "user", "content": f"Question{i}{pad}"})
        msgs.append({"role": "assistant", "content": f"Answer{i}{pad}"})
    return msgs


@pytest.mark.asyncio
async def test_compact_cooldown_releases_with_new_material() -> None:
    llm = _SummarizerLLM(reply="Notes")
    first = await compact_with_summary(
        _padded_history(turns=4), 100000, llm=llm, keep_recent=2, force=True
    )
    grown = first + _turns_only(_padded_history(turns=4))
    max_tokens = int(estimate_messages_tokens(grown) / 0.5)
    out = await compact_with_summary(grown, max_tokens, llm=llm, keep_recent=2)
    summaries = [
        m for m in out
        if m["role"] == "system" and str(m.get("content", "")).startswith("[Conversation Minutes]")
    ]
    assert len(summaries) == 1
    assert llm.chat_calls, "8 fresh turns must re-compact"


@pytest.mark.asyncio
async def test_compact_cooldown_yields_to_urgency_and_force() -> None:
    """Near-full windows and explicit force bypass the cooldown."""
    llm = _SummarizerLLM(reply="Notes")
    first = await compact_with_summary(
        _padded_history(turns=4), 100000, llm=llm, keep_recent=2, force=True
    )
    grown = first + _turns_only(_padded_history(turns=1))
    calls = len(llm.chat_calls)
    # 97% occupancy: over the gate and over the urgency line, so the cooldown
    # must yield even though barely anything is new. Aggressive keeps the
    # window at the latest turn, so the grown history has something to fold.
    from realmock.platform.capabilities.ai.context.options import CompactionOptions

    urgent_max = int(estimate_messages_tokens(grown) / 0.97)
    urgent = await compact_with_summary(
        grown, urgent_max, llm=llm, keep_recent=2,
        options=CompactionOptions(intensity="aggressive", retain=0),
    )
    assert len(llm.chat_calls) > calls, "near-full window must call the summarizer despite cooldown"
    assert any(
        m.get("role") == "system" and str(m.get("content", "")).startswith("[Conversation Minutes]")
        for m in urgent
    )
    forced = await compact_with_summary(grown, 100000, llm=llm, keep_recent=2, force=True)
    summaries = [
        m for m in forced
        if m["role"] == "system" and str(m.get("content", "")).startswith("[Conversation Minutes]")
    ]
    assert len(summaries) == 1, "manual force must always attempt the summary"


def test_compaction_event_carries_window_and_threshold() -> None:
    from realmock.domains.prep.agents.chat import compaction_event

    before = [{"role": "user", "content": "hello there friend"}]
    after = [
        {"role": "system", "content": "[Conversation Minutes] notes"},
        {"role": "user", "content": "hello there friend"},
    ]
    event = compaction_event(before, after, {}, context_window=8000, threshold=0.5)
    assert event is not None
    assert event["summarized"] is True
    assert event["context_window"] == 8000
    assert event["threshold"] == 0.5
    assert compaction_event(before, before, {}) is None


def test_compaction_options_resolve_never_raises() -> None:
    from realmock.platform.capabilities.ai.context.options import CompactionOptions

    opts = CompactionOptions.resolve(intensity="turbo", directive=123, retain=-5)
    assert opts.intensity == "balanced"
    assert opts.directive == ""
    assert opts.retain == CompactionOptions().retain
    assert CompactionOptions.resolve(retain=9999).retain <= 9999
    from realmock.platform.capabilities.ai.context.options import MAX_RETAIN

    assert CompactionOptions.resolve(retain=10**9).retain == MAX_RETAIN
    assert CompactionOptions.resolve(intensity="aggressive", retain=3).keep_window() == 3
    # Intensity floors raise the verbatim tail above a small retain.
    assert CompactionOptions.resolve(intensity="light", retain=0).keep_window() == 10
    assert CompactionOptions.resolve(intensity="balanced", retain=0).keep_window() == 4


def test_provenance_round_trip() -> None:
    from realmock.platform.capabilities.ai.context.summarize import (
        format_provenance,
        parse_provenance,
        strip_provenance,
    )

    trailer = format_provenance(version=2, backup_session_id=7, fork_point=12, focus="errors")
    parsed = parse_provenance(f"[Conversation Minutes] notes\n{trailer}")
    assert parsed == {"v": 2, "backup_session": 7, "fork_point": 12, "focus": "errors"}
    assert parse_provenance("plain text") == {}
    assert parse_provenance("[provenance v=bogus]") == {}
    assert strip_provenance(f"notes\n{trailer}") == "notes"


@pytest.mark.asyncio
async def test_compact_trailer_records_measured_delta() -> None:
    """The stamped trailer carries the mechanical before/after for the card."""
    from realmock.platform.capabilities.ai.context.summarize import parse_provenance

    llm = _SummarizerLLM(reply="Notes")
    msgs = _small_history(turns=4)
    before = estimate_messages_tokens(msgs)
    out = await compact_with_summary(msgs, 100000, llm=llm, keep_recent=2, force=True)
    block = next(
        m for m in out
        if m["role"] == "system" and str(m.get("content", "")).startswith("[Conversation Minutes]")
    )
    parsed = parse_provenance(str(block["content"]))
    assert parsed["v"] == 1
    assert parsed["before"] == before
    # The stamped after-count is measured against a placeholder trailer, so it
    # drifts by the trailer's own tokens; mechanical estimates are approximate
    # by design, and the direction (down) is what the card promises.
    assert abs(parsed["after"] - estimate_messages_tokens(out)) <= 30
    assert parsed["after"] < parsed["before"]


@pytest.mark.asyncio
async def test_compact_default_focus_anchors_summary_without_directive() -> None:
    """No directive: the session objective still steers the summary."""
    llm = _SummarizerLLM(reply="Notes")
    await compact_with_summary(
        _small_history(turns=4), 100000, llm=llm, keep_recent=2, force=True,
        default_focus="Session objective: interview prep for Backend Engineer.",
    )
    assert llm.chat_calls
    assert "Backend Engineer" in llm.chat_calls[0][0]["content"]


@pytest.mark.asyncio
async def test_compact_keep_from_pins_current_round() -> None:
    """Agent-invoked mid-turn compaction must keep everything from keep_from on."""
    llm = _SummarizerLLM(reply="Notes")
    msgs = _small_history(turns=4)
    out = await compact_with_summary(msgs, 100000, llm=llm, force=True, keep_from=6)
    assert llm.chat_calls
    summaries = [
        m for m in out
        if m["role"] == "system" and str(m.get("content", "")).startswith("[Conversation Minutes]")
    ]
    assert len(summaries) == 1
    tail = [m for m in out if m.get("role") != "system"]
    # Pin guarantee: everything from keep_from on stays; the retain window may keep more.
    assert [m.get("content") for m in tail[-2:]] == ["Question3", "Answer3"]
    assert not any(
        m.get("role") == "user" and m.get("content") == "Question0" for m in out
    )


@pytest.mark.asyncio
async def test_compact_keep_from_covering_all_returns_unchanged() -> None:
    llm = _SummarizerLLM(reply="Notes")
    msgs = _small_history(turns=2)
    out = await compact_with_summary(msgs, 100000, llm=llm, force=True, keep_from=0)
    assert out == msgs
    assert llm.chat_calls == []


@pytest.mark.asyncio
async def test_summarize_chunks_long_histories_with_visible_marker() -> None:
    """Beyond the per-call snippet cap, history is chained — never silently dropped."""
    llm = _SummarizerLLM(reply="Chunk notes")
    msgs: list[dict] = [{"role": "system", "content": "Rules"}]
    for i in range(80):
        msgs.append({"role": "user", "content": f"Topic{i} " + "Body" * 50})
        msgs.append({"role": "assistant", "content": f"Reply{i} " + "Detail" * 50})
    out = await compact_with_summary(msgs, 500, llm=llm, keep_recent=4, force=True)
    assert len(llm.chat_calls) > 1, "long history must take multiple chained summary calls"
    summaries = [
        m for m in out
        if m["role"] == "system" and str(m.get("content", "")).startswith("[Conversation Minutes]")
    ]
    assert len(summaries) == 1
    assert "Chunk notes" in summaries[0]["content"]


@pytest.mark.asyncio
async def test_summarize_marks_images_instead_of_dropping() -> None:
    llm = _SummarizerLLM(reply="Notes")
    msgs = (
        [{"role": "system", "content": "Rules"}]
        + _small_history(turns=1)
        + [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:x"}}]}]
        + _small_history(turns=2)
    )
    await compact_with_summary(msgs, 100000, llm=llm, keep_recent=2, force=True)
    assert llm.chat_calls
    prompt = llm.chat_calls[0][0]["content"]
    assert "image(s)" in prompt


def _small_history(turns: int = 4) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": "Rules"}]
    for i in range(turns):
        msgs.append({"role": "user", "content": f"Question{i}"})
        msgs.append({"role": "assistant", "content": f"Answer{i}"})
    return msgs


@pytest.mark.asyncio
async def test_compact_force_summarizes_below_threshold() -> None:
    """Manual /compact must call the LLM even when usage is far below threshold."""
    llm = _SummarizerLLM(reply="Session goal: plan the interview")
    out = await compact_with_summary(
        _small_history(), 100000, llm=llm, keep_recent=2, force=True
    )
    assert llm.chat_calls, "forced compaction must always attempt an LLM summary"
    summaries = [
        m for m in out
        if m["role"] == "system" and str(m.get("content", "")).startswith("[Conversation Minutes]")
    ]
    assert len(summaries) == 1
    assert "Session goal" in summaries[0]["content"]


@pytest.mark.asyncio
async def test_compact_force_folds_short_session_to_latest_turn() -> None:
    """Manual /compact on a short session (fits the auto window) keeps only the latest turn."""
    llm = _SummarizerLLM(reply="Session goal: sorting practice")
    pad = "Detail" * 100
    msgs: list[dict] = [{"role": "system", "content": "Rules"}]
    for i in range(3):
        msgs.append({"role": "user", "content": f"Question{i} {pad}"})
        msgs.append({"role": "assistant", "content": f"Answer{i} {pad}"})
    before = estimate_messages_tokens(msgs)
    out = await compact_with_summary(msgs, 100000, llm=llm, force=True)
    assert llm.chat_calls, "forced compaction must summarize even below threshold"
    summaries = [
        m for m in out
        if m["role"] == "system" and str(m.get("content", "")).startswith("[Conversation Minutes]")
    ]
    assert len(summaries) == 1
    # Latest turn stays verbatim; older turns are folded into the summary.
    assert out[-2:] == msgs[-2:]
    assert not any(
        m.get("content") == "Question0" for m in out if m.get("role") == "user"
    )
    assert estimate_messages_tokens(out) < before


@pytest.mark.asyncio
async def test_compact_no_gain_returns_unchanged() -> None:
    """Auto-compaction whose summary would grow history keeps the original.

    The summarizer call itself still runs (only the persist is skipped), so
    the LLM fires once but the stored history is byte-identical.
    """
    from realmock.platform.capabilities.ai.context.options import CompactionOptions

    # Omitted (~3×79) clears the fold floor while the bloated reply (~305)
    # exceeds the folded amount: persisting it would grow the context.
    llm = _SummarizerLLM(reply="Session objectives: x" + "y" * 1200)
    pad = " Body" * 60
    msgs: list[dict] = [{"role": "system", "content": "Rules"}]
    for i in range(2):
        msgs.append({"role": "user", "content": f"Question{i}{pad}"})
        msgs.append({"role": "assistant", "content": f"Answer{i}{pad}"})
    opts = CompactionOptions.resolve(intensity="aggressive", retain=0)
    out = await compact_with_summary(msgs, 100, llm=llm, keep_recent=1, options=opts)
    assert len(llm.chat_calls) == 1
    assert out == msgs


@pytest.mark.asyncio
async def test_compact_force_folds_single_exchange_whole() -> None:
    """Manual /compact is user-decided: a lone remaining exchange folds whole."""
    llm = _SummarizerLLM(reply="Notes")
    msgs = _small_history(turns=1)
    out = await compact_with_summary(msgs, 100000, llm=llm, force=True)
    assert llm.chat_calls, "manual run must summarize even a single exchange"
    assert any(
        m.get("role") == "system" and str(m.get("content", "")).startswith("[Conversation Minutes]")
        for m in out
    )
    assert not any(m.get("role") in ("user", "assistant") for m in out)


@pytest.mark.asyncio
async def test_compact_force_llm_failure_raises_instead_of_truncating() -> None:
    """Manual /compact must fail loudly, never silently truncate history."""
    llm = _SummarizerLLM(error=RuntimeError("llm down"))
    with pytest.raises(RuntimeError):
        await compact_with_summary(_small_history(), 100000, llm=llm, keep_recent=2, force=True)


@pytest.mark.asyncio
async def test_compact_custom_threshold_gates_llm_summary() -> None:
    """The settings threshold (50–90%) decides when auto-compaction summarizes."""
    big = "contentcontentcontentcontentcontentcontentcontentcontent" * 5
    msgs = [{"role": "user", "content": big + str(i)} for i in range(8)]
    total = sum(estimate_messages_tokens([m]) for m in msgs)
    max_tokens = int(total / 0.45)  # ~45% occupancy
    quiet = _SummarizerLLM(reply="Notes")
    out = await compact_with_summary(msgs, max_tokens, llm=quiet, threshold=0.9, keep_recent=2)
    assert quiet.chat_calls == [], "45% usage must not summarize at a 90% threshold"
    assert out == msgs
    loud = _SummarizerLLM(reply="Notes")
    out = await compact_with_summary(msgs, max_tokens, llm=loud, threshold=0.3, keep_recent=2)
    assert loud.chat_calls, "45% usage must summarize at the 30% auto threshold"


@pytest.mark.asyncio
async def test_compact_invalid_threshold_falls_back_to_default() -> None:
    """Garbage thresholds never disable compaction; the agent default applies."""
    llm = _SummarizerLLM(reply="Notes")
    await compact_with_summary(_big_history(), 500, llm=llm, keep_recent=4, threshold=7.0)
    assert llm.chat_calls, "out-of-range threshold must fall back to the default"


def test_compress_messages_never_severs_tool_pairs() -> None:
    """Rule-based folding must not open the kept tail with an orphan tool
    result: its assistant(tool_calls) partner would sit in the folded head and
    providers reject the unpaired tool message with a hard 400."""
    msgs: list = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "OVERVIEW " + "x" * 400},
    ]
    for i in range(16):
        msgs.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": f"c{i}a", "type": "function",
                 "function": {"name": "web_search", "arguments": "{}"}},
                {"id": f"c{i}b", "type": "function",
                 "function": {"name": "github_get_repo", "arguments": "{}"}},
            ],
        })
        msgs.append({"role": "tool", "tool_call_id": f"c{i}a", "content": "A" * 300})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}b", "content": "B" * 300})
    out = compress_messages(msgs, max_tokens=100, keep_recent=32)
    non_system = [m for m in out if m.get("role") != "system"]
    assert non_system[0]["role"] != "tool"
    open_ids: set[str] = set()
    for m in out:
        if m.get("role") == "assistant":
            open_ids = {str(tc.get("id")) for tc in m.get("tool_calls") or []}
        elif m.get("role") == "tool":
            assert m.get("tool_call_id") in open_ids
