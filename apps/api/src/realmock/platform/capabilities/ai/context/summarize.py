"""LLM minutes-style compaction: ``compact_with_summary`` (offline equivalent of terminal Agent auto-compact).

Above the threshold, send omitted conversation to the LLM to generate a sectioned summary that
replaces the old one (incrementally: the previous summary is included as input, preserving information);
if the LLM fails, fall back to a rule-based summary (log a warning, making the degradation visible,
not silent) — unless ``force=True`` (manual ``/compact``), where the failure propagates so the
caller surfaces it instead of silently truncating history. ``llm=None`` is equivalent to rule-based
compaction; below the threshold, return messages unchanged (while still collapsing tool-call pairs)
unless ``force=True``.

Cache discipline: the summarizer call replays the caller's stable system prefix
as its own system message (prefix-KV reuse) with the compression instruction
trailing last; volatile content never enters the prefix.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from realmock.platform.capabilities.ai.agent.working_memory import WorkingMemory
from realmock.platform.capabilities.ai.context.compress import (
    COMPACTION_DIGEST_MARKER,
    COMPACTION_SUMMARY_MARKER,
    _prune_stale_tool_pairs,
)
from realmock.platform.capabilities.ai.context.estimation import (
    _omitted_digest,
    _plain_text,
    estimate_messages_tokens,
)
from realmock.platform.capabilities.ai.context.options import CompactionOptions
from realmock.platform.capabilities.ai.llm.defaults import COMPACTION_SUMMARY_MAX_TOKENS

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = (
    "Condense the conversation history into structured notes that later turns will rely on."
    "Keep facts, decisions, conclusions, and open items; drop pleasantries, repetition, and procedural filler."
    "Write one to two lines per section and omit empty sections:\n"
    "Session objectives / Confirmed key decisions / User weaknesses and clear requirements / Important findings and conclusions / To-dos and next steps\n"
    "Quote names, numbers, file paths, commands, and error text verbatim; never invent content that is not in the conversation."
    "Do not mention the compression itself; write only the notes."
)

#: Max conversation snippets per summarizer call; longer histories are
#: summarized chunk by chunk (chained) instead of silently dropping the tail.
_SUMMARY_SNIPPETS_PER_CHUNK = 60
#: Upper bound on chained summarizer calls per compaction; beyond this the
#: earliest remainder folds into an explicit counted marker (visible, not silent).
_MAX_SUMMARY_CHUNKS = 6
#: Per-message snippet clip (characters) for the summarizer input.
_SNIPPET_CLIP_CHARS = 200
#: Cooldown: skip the automatic gate while fewer than this many fresh
#: non-system messages arrived since the last summary (refolding a barely
#: grown history rewrites the record every turn for ~zero gain). Manual
#: force and near-full windows bypass the cooldown.
_MIN_NEW_SINCE_COMPACT = 4
#: Near-full fraction that bypasses the cooldown (urgency over thrift).
_URGENT_RATIO = 0.95
#: Minimum foldable tokens for an automatic run: a summary block itself costs
#: a few hundred tokens, so folding less can never win — skip before spending
#: the summarizer call. Manual force bypasses (explicit user intent).
_MIN_OMITTED_TOKENS = 200

#: Machine-readable provenance trailer appended to summary blocks (no migration
#: needed to link a backup session and fork point to the summary that replaced them).
_PROVENANCE_MARKER = "[provenance"

#: Legacy/alternate summary markers: recognized as previous-summary input for
#: incremental updates and superseded (replaced, never duplicated) on write.
_LEGACY_SUMMARY_MARKER = "[Session summary]"

_PREVIOUS_SUMMARY_MARKERS = (
    COMPACTION_SUMMARY_MARKER,
    COMPACTION_DIGEST_MARKER,
    _LEGACY_SUMMARY_MARKER,
)


def format_provenance(
    *,
    version: int = 1,
    backup_session_id: int | None = None,
    fork_point: int | None = None,
    focus: str = "",
    before: int | None = None,
    after: int | None = None,
    base: int | None = None,
) -> str:
    """Render the provenance trailer for a summary block (all fields optional)."""
    parts = [f"v={max(1, int(version or 1))}"]
    if backup_session_id is not None:
        parts.append(f"backup_session={int(backup_session_id)}")
    if fork_point is not None:
        parts.append(f"fork_point={max(0, int(fork_point))}")
    if focus:
        parts.append(f"focus={str(focus)[:80]}")
    if before is not None:
        parts.append(f"before={max(0, int(before))}")
    if after is not None:
        parts.append(f"after={max(0, int(after))}")
    if base is not None:
        parts.append(f"base={max(0, int(base))}")
    return f"{_PROVENANCE_MARKER} {' '.join(parts)}]"


def parse_provenance(text: str) -> dict[str, Any]:
    """Extract the provenance trailer from a summary block (empty dict when absent)."""
    out: dict[str, Any] = {}
    try:
        start = str(text or "").rfind(_PROVENANCE_MARKER)
        if start < 0:
            return out
        body = str(text)[start + len(_PROVENANCE_MARKER):].strip().rstrip("]").strip()
        for token in body.split():
            if "=" not in token:
                continue
            key, _, value = token.partition("=")
            out[key] = value
        for key in ("v", "backup_session", "fork_point", "before", "after", "base"):
            if key in out:
                try:
                    out[key] = int(str(out[key]))
                except (TypeError, ValueError):
                    del out[key]
    except Exception:
        return {}
    return out


def strip_provenance(text: str) -> str:
    """Remove the provenance trailer for display (the stored block keeps it)."""
    raw = str(text or "")
    start = raw.rfind(_PROVENANCE_MARKER)
    if start < 0:
        return raw.strip()
    return raw[:start].strip()


def _previous_summary_text(system: list[dict[str, Any]]) -> str:
    """Get the text of the previous LLM record (the input of incremental compression); if not, the empty string."""
    for m in reversed(system):
        content = m.get("content")
        if isinstance(content, str) and content.startswith(_PREVIOUS_SUMMARY_MARKERS):
            body = content
            for marker in _PREVIOUS_SUMMARY_MARKERS:
                if body.startswith(marker):
                    body = body[len(marker):]
                    break
            return strip_provenance(body.strip())
    return ""


def _without_prior_summaries(system: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop previous summary-like blocks so the new record supersedes (never duplicates) them."""
    return [
        m
        for m in system
        if not (
            isinstance(m.get("content"), str)
            and str(m.get("content")).startswith(_PREVIOUS_SUMMARY_MARKERS)
        )
    ]


def _previous_summary_base(system: list[dict[str, Any]]) -> int | None:
    """Non-system count retained by the previous summary (None when no record)."""
    for m in reversed(system):
        content = m.get("content")
        if isinstance(content, str) and content.startswith(COMPACTION_SUMMARY_MARKER):
            base = parse_provenance(content).get("base")
            return int(base) if isinstance(base, int) else None
    return None


def _previous_summary_version(system: list[dict[str, Any]]) -> int:
    """Provenance version of the previous summary (0 when none)."""
    for m in reversed(system):
        content = m.get("content")
        if isinstance(content, str) and content.startswith(COMPACTION_SUMMARY_MARKER):
            version = parse_provenance(content).get("v", 0)
            return int(version) if isinstance(version, int) else 0
    return 0


def _count_images(content: Any) -> int:
    """Count image parts in multimodal content (they carry no text for the summarizer)."""
    if not isinstance(content, list):
        return 0
    total = 0
    for item in content:
        if isinstance(item, dict) and item.get("image_url") is not None:
            total += 1
    return total


def _transcript_lines(omitted: list[dict[str, Any]]) -> list[str]:
    """Serialize omitted messages to short snippets (images become explicit markers, never silent drops)."""
    lines: list[str] = []
    for m in omitted:
        snippet = _plain_text(m.get("content")).replace("\n", " ").strip()
        images = _count_images(m.get("content"))
        if images and not snippet:
            snippet = f"[{images} image(s) shared, content not textual]"
        elif images:
            snippet = f"{snippet} [+{images} image(s)]"
        if not snippet:
            continue
        if len(snippet) > _SNIPPET_CLIP_CHARS:
            snippet = snippet[: _SNIPPET_CLIP_CHARS - 1] + "…"
        lines.append(f"{m.get('role')}: {snippet}")
    return lines


async def _summarize_transcript(
    llm: Any,
    prior: str,
    omitted: list[dict[str, Any]],
    options: CompactionOptions,
    *,
    prefix_blocks: list[str] | None = None,
    default_focus: str | None = None,
    report: dict[str, Any] | None = None,
) -> str:
    """Let LLM generate (incrementally updated) sectioned session minutes. Failure is rolled back by the caller.

    Long histories are summarized chunk by chunk (prior chains forward); when
    chunks exceed ``_MAX_SUMMARY_CHUNKS`` the earliest remainder folds into an
    explicit counted marker instead of vanishing. The stable system prefix is
    replayed as the call's system message so prefix caches keep hitting; the
    compression instruction always trails last. Token/latency cost lands in
    ``report`` when provided (usage-snapshot deltas, never raising).
    """
    lines = _transcript_lines(omitted)
    chunks = [
        lines[i: i + _SUMMARY_SNIPPETS_PER_CHUNK]
        for i in range(0, max(1, len(lines)), _SUMMARY_SNIPPETS_PER_CHUNK)
    ]
    remainder_note = ""
    if len(chunks) > _MAX_SUMMARY_CHUNKS:
        dropped_snippets = sum(len(c) for c in chunks[:-_MAX_SUMMARY_CHUNKS])
        remainder_note = (
            f"\n(Earliest {dropped_snippets} conversation snippets folded by count only; "
            "their detail was not re-read.)"
        )
        chunks = chunks[-_MAX_SUMMARY_CHUNKS:]
    instruction_parts = [_SUMMARY_PROMPT, options.detail_hint()]
    effective_focus = options.directive or (default_focus or "")
    if effective_focus:
        instruction_parts.append(
            "Compression focus for this run (prioritize these, still keep the section structure):\n"
            + effective_focus
        )
    instruction = "\n".join(instruction_parts)
    system_prefix = "\n\n".join(b for b in (prefix_blocks or []) if b) or None

    summary = prior
    for chunk in chunks:
        parts: list[str] = []
        if summary:
            parts.append(
                "Previous record (please update incrementally based on it and do not lose information that is still valid):\n"
                + summary
            )
        parts.append("Conversations that need to be compressed:\n" + "\n".join(chunk))
        if remainder_note and chunk is chunks[0]:
            parts.append(remainder_note.strip())
        parts.append(instruction)
        started = time.perf_counter()
        usage_before = _usage_snapshot(llm)
        try:
            text = await llm.chat(
                [{"role": "user", "content": "\n\n".join(parts)}],
                system=system_prefix,
                temperature=0.2,
                max_tokens=COMPACTION_SUMMARY_MAX_TOKENS,
                purpose="compaction",
            )
        finally:
            if report is not None:
                try:
                    report["latency_ms"] = report.get("latency_ms", 0.0) + (time.perf_counter() - started) * 1000.0
                    for key, value in _usage_delta(llm, usage_before).items():
                        report[key] = report.get(key, 0) + value
                except Exception:
                    pass
        summary = str(text or "").strip()
        if not summary:
            break
    return summary


def _usage_snapshot(llm: Any) -> dict[str, int]:
    """Best-effort usage counters snapshot (empty when the LLM exposes none)."""
    try:
        usage = getattr(llm, "usage", None)
        if usage is None:
            return {}
        data = usage.to_dict() if hasattr(usage, "to_dict") else {}
        return {k: int(v or 0) for k, v in dict(data).items() if isinstance(v, (int, float))}
    except Exception:
        return {}


def _usage_delta(llm: Any, before: dict[str, int]) -> dict[str, int]:
    """Non-negative per-key usage growth since ``before`` (floored at zero)."""
    after = _usage_snapshot(llm)
    delta: dict[str, int] = {}
    for key in set(before) | set(after):
        growth = after.get(key, 0) - before.get(key, 0)
        if growth > 0:
            delta[key] = growth
    return delta


async def compact_with_summary(
    messages: list[dict[str, Any]],
    max_tokens: int,
    *,
    memory: WorkingMemory | None = None,
    llm: Any = None,
    keep_recent: int = 20,
    threshold: float = 0.3,
    force: bool = False,
    options: CompactionOptions | None = None,
    keep_from: int | None = None,
    provenance: dict[str, Any] | None = None,
    default_focus: str | None = None,
    report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """LLM summary-style compression (the offline equivalent of terminal Agent auto-compact).

    When the threshold is exceeded: first collapse old tool-call pairs, then give the omitted conversation to the LLM to generate a sectioned summary
    that replaces the old summary (incrementally: the previous summary is included as input, so no information is lost). If the LLM fails, fall back
    to a rule-based summary (record a warning so the degradation is visible rather than silent) — unless ``force`` is set, in which case the error
    propagates so manual ``/compact`` fails loudly instead of truncating. Return the input unchanged when it is below the threshold, unless ``force``
    is set (manual ``/compact`` is user-decided: it always attempts an LLM
    summary while any history exists).
    Agents with an LLM instance should call this at the start of each round; with ``llm=None``, it is equivalent to rule-based compression.

    ``options`` carries intensity/directive/retain: the verbatim tail is
    ``max(retain, intensity floor)``; under ``force`` an explicit manual run
    folds to the latest turn regardless of that window (a lone exchange folds
    whole).
    ``keep_from`` (agent-invoked mid-turn compaction) pins the cutoff: every
    message from that non-system index on stays verbatim so in-flight tool
    pairs never split. ``provenance`` stamps the summary trailer
    (version/backup/fork-point); cost lands in ``report``.
    """
    opts = options or CompactionOptions()
    system = [m for m in messages if m.get("role") == "system"]
    rest = _prune_stale_tool_pairs(
        [m for m in messages if m.get("role") != "system"]
    )
    if not isinstance(threshold, (int, float)) or not 0 < threshold < 1:
        threshold = 0.3
    # The old tool takes effect unconditionally on folding (micro-compression); LLM records are only generated when the threshold is exceeded
    # (or always, when forced by manual /compact). The entry estimate doubles
    # as the trailer's before-count, so the card can show the true delta.
    before_est = estimate_messages_tokens(system + rest)
    if not force and max_tokens > 0 and before_est <= max_tokens * threshold:
        return system + rest
    if not force and max_tokens > 0:
        # Cooldown against chronic re-compaction: the previous turn already
        # wrote a summary and barely any fresh turns arrived, so refolding
        # now would rewrite the record for ~zero gain while spending a
        # summarizer call (and its latency) every turn. Near-full windows
        # stay urgent and bypass the cooldown.
        base = _previous_summary_base(system)
        if (
            base is not None
            and len(rest) - base < _MIN_NEW_SINCE_COMPACT
            and before_est <= max_tokens * _URGENT_RATIO
        ):
            return system + rest
    keep = max(keep_recent, opts.keep_window())
    if force:
        # Manual /compact is user-decided: fold everything older than the
        # latest turn regardless of the retain window. A single remaining
        # exchange folds whole, so a manual run always produces a summary
        # while any history exists (only an empty history stays a no-op).
        keep = 2
        if 0 < len(rest) <= 2:
            keep = 0
    start = max(0, len(rest) - keep)
    if keep_from is not None:
        # Pin semantics: everything from keep_from on stays verbatim, while
        # the retain window still holds — hence the minimum of both cutoffs.
        try:
            pinned = max(0, int(keep_from))
        except (TypeError, ValueError):
            pinned = 0
        start = min(pinned, start)
    trimmed = rest[start:]
    omitted = rest[:start]
    if report is not None:
        # Exact fold cutoff as a backend message index (clients archive
        # everything older for display). Equality scan with a safe fallback:
        # a duplicate-content mismatch only keeps more visible, never less.
        try:
            kept_from: int | None = None
            if trimmed:
                needle = trimmed[0]
                for i, m in enumerate(messages):
                    if m is needle:
                        kept_from = i
                        break
                if kept_from is None:
                    for i, m in enumerate(messages):
                        if m == needle:
                            kept_from = i
                            break
                if kept_from is None:
                    kept_from = len(messages)
            else:
                kept_from = len(messages)
            report["kept_from"] = kept_from
        except Exception:
            pass
    if not omitted:
        # Token estimate can exceed the threshold because of large pinned messages
        # (e.g. vision page images) without any older turns to summarize.
        return system + rest
    if not force and estimate_messages_tokens(omitted) < _MIN_OMITTED_TOKENS:
        # Nothing worth folding: the summary block alone would cost more.
        return system + rest
    if memory is not None:
        memory.absorb_omitted(omitted)

    # There is no way to omit the conversation. If the minutes are not entered, go directly to the rule summary path.
    summary_text = ""
    if omitted and llm is not None:
        try:
            prefix_blocks = [str(m.get("content") or "") for m in system[:1]]
            summary_text = await _summarize_transcript(
                llm, _previous_summary_text(system), omitted, opts,
                prefix_blocks=prefix_blocks, default_focus=default_focus, report=report,
            )
        except Exception as e:
            if force:
                # Manual /compact must be LLM-summarized, never truncated:
                # let the caller surface the failure instead of degrading.
                raise
            logger.warning("LLM session record failed, rollback rule summary: %s", e)
            summary_text = ""

    if summary_text:
        kept_system = _without_prior_summaries(system)
        # Draft with a placeholder trailer first so the recorded delta is
        # honest, then stamp the real trailer (same shape, negligible drift).
        draft_block = {"role": "system", "content": f"{COMPACTION_SUMMARY_MARKER} {summary_text}\n{_PROVENANCE_MARKER} v=1]"}
        after_est = estimate_messages_tokens(kept_system + [draft_block] + trimmed)
        if not force and after_est >= before_est:
            # Folding a tiny history costs a summary block plus suffixes while
            # removing almost nothing: keep the original instead of growing
            # the context to "compact" it.
            return system + rest
        trailer = format_provenance(
            version=_previous_summary_version(system) + 1,
            backup_session_id=(provenance or {}).get("backup_session_id"),
            fork_point=(provenance or {}).get("fork_point"),
            focus=opts.directive or (default_focus or ""),
            before=before_est,
            after=after_est,
            base=len(trimmed),
        )
        return kept_system + [
            {"role": "system", "content": f"{COMPACTION_SUMMARY_MARKER} {summary_text}\n{trailer}"}
        ] + trimmed

    digest = _omitted_digest(omitted)
    body = (
        f"[Context compression] The earliest {len(omitted)} messages are omitted; "
        f"the latest {len(trimmed)} are kept verbatim."
    )
    if digest:
        body += "\nSummary:\n" + digest
    # Rule fallback does not chain prior records into the new note, so older
    # summary-like blocks stay (unlike the LLM path above, which supersedes
    # after folding the previous record in). The trailer still records the
    # measured delta for the card.
    after_est = estimate_messages_tokens(system + trimmed) + estimate_messages_tokens(
        [{"role": "system", "content": body}]
    )
    body += "\n" + format_provenance(before=before_est, after=after_est, base=len(trimmed))
    return system + [{"role": "system", "content": body}] + trimmed
