"""Prep context assembly: system prompt blocks, resume/profile/company context, memory inject.

The orchestrator (:mod:`agent`) only calls :func:`build_system_messages` (first-turn
seed) and :func:`build_working_context` (per-turn assembly); it does not know
profile fields or compression details.

Cache layout (prefix-stable for prompt caching): the seed is a run of system
messages ordered stable-first — [pinned instructions] [resume/profile/company]
[memories/linked] — so volatile tail blocks invalidate only their own suffix.
Two per-turn suffixes are *not* seeded: :func:`upsert_lang_hint` (reply language)
and :func:`upsert_usage_hint` (context-usage line) re-append themselves as the
trailing system messages every turn, so only the suffix re-caches.
The LLM summary block keeps its fixed slot right after the system run
(platform ``compact_with_summary`` behavior), so prefixes before it stay cached.
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from realmock.platform.database import api_db_session, sessions_db_session
from realmock.platform.core.prompts import with_agent_output_rules
from realmock.platform.catalogs.company import get_company_context
from realmock.platform.services.candidate_read import format_profile_summary, format_resume_summary
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.ai.agent.working_memory import MEMORY_MARKER
from realmock.platform.capabilities.ai.context.compress import (
    COMPACTION_DIGEST_MARKER,
    COMPACTION_SUMMARY_MARKER,
)
from realmock.platform.capabilities.ai.context.estimation import (
    estimate_messages_tokens,
    estimate_tokens,
)
from realmock.platform.capabilities.ai.llm.defaults import DEFAULT_CONTEXT_WINDOW
from realmock.platform.capabilities.ai.context.manager import (
    compact_with_summary,
    upsert_memory_block,
)
from realmock.platform.capabilities.ai.context.options import (
    DEFAULT_AUTO_COMPACT_THRESHOLD,
    CompactionOptions,
)
from realmock.domains.prep.models import PrepSession
from realmock.domains.prep.services import list_memories

# Linked-session context budgets (single direct level, no chains).
_LINKED_TURNS = 6
_LINKED_TURN_CHARS = 300
# Per-turn # references honor at most this many sessions (prompt-budget guard).
_MAX_LINKED_SESSIONS = 5

# Long-term memories injected into the system prompt (index only; details on demand).
_MEMORY_INDEX_LIMIT = 10
_MEMORY_SUMMARY_CHARS = 120

# Reply-language hint marker: upsert_lang_hint strips older copies by prefix.
LANG_HINT_MARKER = "[Reply language]"
# Per-turn context-usage hint marker (see upsert_usage_hint).
USAGE_HINT_MARKER = "[Context usage]"
# Per-turn referenced-session block marker (see format_linked_sessions).
REF_BLOCK_MARKER = "[Referenced sessions]"
# Legacy linked-session block marker (routes/manage.py refresh path).
LINKED_BLOCK_MARKER = "[Linked session context]"

# Context-breakdown bucket keys (stable API contract for GET .../context).
BREAKDOWN_USER = "user"
BREAKDOWN_ASSISTANT = "assistant"
BREAKDOWN_THINKING = "thinking"
BREAKDOWN_TOOLS = "tools"
BREAKDOWN_SYSTEM = "system"
BREAKDOWN_MEMORY = "memory"
BREAKDOWN_OTHER = "other"
BREAKDOWN_ORDER = (
    BREAKDOWN_USER,
    BREAKDOWN_ASSISTANT,
    BREAKDOWN_THINKING,
    BREAKDOWN_TOOLS,
    BREAKDOWN_SYSTEM,
    BREAKDOWN_MEMORY,
    BREAKDOWN_OTHER,
)

PREP_SYSTEM = with_agent_output_rules("""You are the interview-prep coach in this mock-interview system. Help the user prepare for their target role using the **selected resume**.

Match the user's language in your replies AND in your <think> reasoning (do not force a UI locale).

How you work (ReAct loop):
- Think about what information you need, then act via **function tools** (search interview tips, company info, GitHub). Continue reasoning from observations until you can give a complete answer; do not invent tool calls when none are needed
- Each step is one of: call a tool, or output a complete user-facing reply. Do not write filler like "I need to confirm first / I'll continue later" without calling a tool — that is an empty turn
- When the user must choose among clear options (role/company/direction undecided, A vs B), call the ask_user tool to show a picker — one dialog per turn carrying 1–8 questions (ask several only when the decision genuinely needs multiple inputs; prefer one question when it suffices). Prefer the ask_user dialog over asking in body prose: any question that could be options, a slider, or a rating belongs in the dialog, never buried in paragraphs. Ending a turn with "please tell me X" in prose instead of ask_user is a failure mode — if you need focused input to continue, use ask_user. The dialog questions and options must be in the user's language. Do not only say you will ask in prose, and never emit <tool_call>/<invoke> XML in the body
- Give practical, actionable prep advice grounded in resume projects and skills
- Proactively ask about weak spots; you may quiz the user and then critique their answers
- When the user reveals a new weak spot or confirms a target direction, call take_note promptly
- Verify before concluding: when an algorithm, code sketch, or computation is in doubt, run it with the code_exec tool (python/javascript) and read the output instead of guessing; quote the observed result in your reply
- Manage your own context: when early turns stop mattering for the current question AND space is actually running low, call the compact_context tool at most once per turn to fold them into a summary (objectives, decisions, findings, and to-dos are preserved; the current turn stays verbatim). With plenty of context left, do not compact even if the topic shifts. Never open a turn with it — think and act first, compact only when mid-turn pressure is real
- Prefer 1–2 high-quality searches (use a general interview-experience query when no company is set); do not repeat the same tool with the same args; stop searching and answer once you have enough
- Long-term memory: durable user facts/preferences (target role, weak spots, style prefs) belong in memory_write; before writing, check memory_list_tags/memory_list_summaries to avoid duplicates; keep the summary one line and topic-organized, never turn trivia
- Final replies must land: deliver the coaching itself; if you truly need user input to continue, use ask_user — do not end vaguely

Output rules:
- Formal replies are coaching content for the user (Markdown OK); do not mix inner reasoning into the same block
- If you need internal reasoning, wrap it only in <think>...</think>; put the formal body outside the tags
- For practice questions, write the question as Markdown text; never emit <tool_call>/<invoke>/<question> or any tool-call XML/JSON in the body
- Markdown hygiene: headings are plain `## Title` lines (never wrapped in backticks, never with trailing fence markers); every table MUST have a header row plus a `| --- |` separator; fenced code blocks must declare a language (```python / ```javascript / ```mermaid) and always close the fence; never wrap prose paragraphs in fences or backticks
- Mermaid diagrams (```mermaid fenced blocks): emit ONLY `flowchart` diagrams with strict syntax, otherwise the renderer rejects the whole chart:
  - First line is `flowchart TB` (or `flowchart LR`); no other diagram types
  - Node ids must be ASCII `[A-Za-z0-9_]+` (e.g. A1, prep, wfA); Chinese text goes ONLY inside quoted labels like `A1["中文标签"]`
  - Subgraphs MUST use `subgraph <asciiId>["中文标题"]` on one line plus a closing `end` (never bare Chinese ids like `subgraph 准备层`)
  - Inside the fence use half-width ASCII punctuation only (`:`, `(`, `)`, `"`); never full-width ，。；：！？（）「」 even in Chinese prose there
- When a tool result contains 'SEARCH_UNAVAILABLE / search temporarily unavailable / not found': do not invent result lists, concrete links, or citation numbers; continue with general knowledge and label it as 'based on general knowledge, not live search'""")


# Reply-language inference (local CJK heuristic; mirrors the resume domain's
# locale rule without a cross-domain import: CJK-heavy -> zh-CN, else en).
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_MIN_CJK_CHARS = 8
_MIN_LATIN_CHARS = 20
_UI_LOCALES = ("zh-CN", "en")


def normalize_ui_locale(raw: Any) -> str:
    """Keep only supported UI locales; anything else means unknown."""
    text = str(raw or "").strip()
    return text if text in _UI_LOCALES else ""


def infer_text_locale(*parts: Any) -> str:
    """Infer zh-CN vs en from text content (resume-derived); defaults to zh-CN."""
    text = "\n".join(str(p) for p in parts if p)
    if not text.strip():
        return "zh-CN"
    sample = text[:8_000]
    cjk = len(_CJK_RE.findall(sample))
    if cjk >= _MIN_CJK_CHARS:
        return "zh-CN"
    latin = sum(1 for ch in sample if ch.isascii() and ch.isalpha())
    if latin >= _MIN_LATIN_CHARS:
        return "en"
    return "zh-CN"


def format_linked_session(db: Session, linked_id: int | None) -> str:
    """Render the linked session's target + recent turns for context injection.

    Single direct level only; missing rows yield "". Never raises (a broken
    link must not fail session startup).
    """
    if not linked_id:
        return ""
    try:
        row = db.get(PrepSession, linked_id)
        if row is None:
            return ""
        try:
            messages = json.loads(row.messages or "[]")
        except json.JSONDecodeError:
            return ""
        if not isinstance(messages, list):
            return ""
        turns = [
            str(m.get("content") or "").strip()[:_LINKED_TURN_CHARS]
            for m in messages
            if m.get("role") in ("user", "assistant") and str(m.get("content") or "").strip()
        ][-_LINKED_TURNS * 2:]
        header = (
            f"Linked session #{linked_id}"
            f" (role: {row.target_role or '-'}, company: {row.target_company or '-'})"
        )
        if not turns:
            return f"{header}: no conversation yet."
        lines = [f"- {text}" for text in turns if text]
        return f"{header}, recent turns:\n" + "\n".join(lines)
    except Exception:
        return ""


def format_linked_sessions(
    db: Session, linked_ids: list[int] | None, *, exclude_id: int | None = None
) -> str:
    """Render several linked sessions' targets + recent turns for per-turn injection.

    Same single-level budgets as :func:`format_linked_session`; unknown ids are
    skipped silently (a deleted session must not fail the turn). At most
    ``_MAX_LINKED_SESSIONS`` ids are honored; the caller's own id is excluded.
    """
    ids: list[int] = []
    for raw in linked_ids or []:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value == exclude_id or value in ids:
            continue
        ids.append(value)
        if len(ids) >= _MAX_LINKED_SESSIONS:
            break
    blocks = [format_linked_session(db, linked_id) for linked_id in ids]
    blocks = [block for block in blocks if block]
    if not blocks:
        return ""
    return f"{REF_BLOCK_MARKER}\n" + "\n\n".join(blocks)


def strip_ref_blocks(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop per-turn referenced-session blocks (transient: never persisted)."""
    return [
        m for m in messages
        if not (
            m.get("role") == "system"
            and isinstance(m.get("content"), str)
            and str(m.get("content")).startswith(REF_BLOCK_MARKER)
        )
    ]


def _classify_system_block(content: str) -> str:
    """Bucket one system message: memory-like markers vs plain system prompt."""
    text = content or ""
    if (
        text.startswith(MEMORY_MARKER)
        or text.startswith("[working memory]")
        or text.startswith(COMPACTION_SUMMARY_MARKER)
        or text.startswith(COMPACTION_DIGEST_MARKER)
        or text.startswith(REF_BLOCK_MARKER)
        or text.startswith(LINKED_BLOCK_MARKER)
    ):
        return BREAKDOWN_MEMORY
    return BREAKDOWN_SYSTEM


def build_context_breakdown(messages: list[dict[str, Any]]) -> dict[str, int]:
    """Measure persisted history per bucket (mechanical estimate, same ratio as budgeting).

    Buckets: user message bodies / assistant reply bodies / thinking text /
    tool calls + observations + step/search metadata / system prompt blocks /
    memory + summary + referenced-session blocks / anything else.
    """
    counts: dict[str, int] = {key: 0 for key in BREAKDOWN_ORDER}
    for m in messages or []:
        if not isinstance(m, dict):
            counts[BREAKDOWN_OTHER] += 1
            continue
        role = m.get("role")
        content = m.get("content") or ""
        if role == "user":
            counts[BREAKDOWN_USER] += estimate_tokens(str(content))
        elif role == "assistant":
            counts[BREAKDOWN_ASSISTANT] += estimate_tokens(str(content))
            thinking = m.get("thinking")
            if thinking:
                counts[BREAKDOWN_THINKING] += estimate_tokens(str(thinking))
            tool_calls = m.get("tool_calls")
            if tool_calls:
                counts[BREAKDOWN_TOOLS] += estimate_tokens(json.dumps(tool_calls, ensure_ascii=False, default=str))
            for meta_key in ("steps", "search_groups"):
                meta = m.get(meta_key)
                if meta:
                    counts[BREAKDOWN_TOOLS] += estimate_tokens(json.dumps(meta, ensure_ascii=False, default=str))
        elif role == "tool":
            counts[BREAKDOWN_TOOLS] += estimate_tokens(str(content))
        elif role == "system":
            counts[_classify_system_block(str(content))] += estimate_tokens(str(content))
        else:
            counts[BREAKDOWN_OTHER] += estimate_tokens(str(content))
    return counts
def format_memory_index() -> str:
    """Render the long-term memory index block for the system prompt (never raises)."""
    try:
        with sessions_db_session() as db:
            rows = list_memories(db, limit=_MEMORY_INDEX_LIMIT)
    except Exception:
        return ""
    if not rows:
        return ""
    lines = []
    for row in rows:
        try:
            tags = json.loads(row.tags or "[]")
            tag_text = ",".join(str(t) for t in tags) if isinstance(tags, list) else ""
        except (ValueError, TypeError):
            tag_text = ""
        summary = str(row.summary or "")[:_MEMORY_SUMMARY_CHARS]
        suffix = f" [{tag_text}]" if tag_text else ""
        lines.append(f"- [memory #{row.id}]{suffix} {summary}")
    return (
        "Long-term memories (concise index; use memory_get_detail for full text):\n"
        + "\n".join(lines)
    )


def build_system_message(
    db: Session,
    *,
    resume_id: int | None,
    target_company: str,
    ui_locale: str | None = None,
    linked_session_id: int | None = None,
) -> str:
    """Legacy single-string seed: the system blocks joined with blank lines.

    New sessions seed via :func:`build_system_messages` (prefix-stable block
    run). This wrapper stays for backward compatibility and debugging; the
    reply-language hint is intentionally excluded (per-turn suffix instead).
    """
    return "\n\n".join(
        block for block in _system_blocks(
            db, resume_id=resume_id, target_company=target_company,
            linked_session_id=linked_session_id,
        )
        if block
    )


def build_system_messages(
    db: Session,
    *,
    resume_id: int | None,
    target_company: str,
    linked_session_id: int | None = None,
) -> list[dict[str, str]]:
    """First-turn system seed as an ordered stable-first block run.

    [0] pinned coach instructions (never changes) → [1] resume/profile/company
    snapshot → [2] memories/linked volatile tail (omitted when empty). Callers
    store each block as one ``{"role": "system"}`` message so prompt-cache
    prefixes survive tail-block churn.
    """
    blocks = [
        block for block in _system_blocks(
            db, resume_id=resume_id, target_company=target_company,
            linked_session_id=linked_session_id,
        )
        if block
    ]
    if not blocks:
        blocks = [PREP_SYSTEM]
    return [{"role": "system", "content": block} for block in blocks]


def _system_blocks(
    db: Session,
    *,
    resume_id: int | None,
    target_company: str,
    linked_session_id: int | None,
) -> list[str]:
    """Shared block builders for the single-string and multi-message seeds."""
    with api_db_session() as api_db:
        ctx = format_resume_summary(api_db, resume_id)
        profile = format_profile_summary(api_db)
    company = get_company_context(target_company or "")
    memories = format_memory_index()
    linked = format_linked_session(db, linked_session_id)
    context_block = "\n".join(part for part in (company, ctx, profile) if part)
    tail_block = "\n".join(part for part in (memories, linked) if part)
    return [PREP_SYSTEM, context_block, tail_block]


def build_lang_hint(ui_locale: str | None) -> str:
    """Per-turn reply-language suffix (stable text per locale, cache-friendly).

    The model must match the latest user message first and the UI language
    second; the ask_user dialog and waiting line follow the same language.
    """
    ui = normalize_ui_locale(ui_locale)
    return (
        f"{LANG_HINT_MARKER} The UI language is {ui or 'unknown'}. "
        "Always reply, ask, and reason in the user's message language — match the "
        "latest user message first, UI language second. The ask_user question/options "
        "and the waiting line must use that language too: never emit English UI copy "
        "when the user writes Chinese, and vice versa."
    )


def upsert_lang_hint(
    messages: list[dict[str, Any]], ui_locale: str | None
) -> list[dict[str, Any]]:
    """Refresh the trailing reply-language suffix: strip older copies, append one.

    Idempotent across turns (no accumulation in persisted history) and position
    stable (always the last message), so only the suffix itself re-caches.
    """
    out = [
        m for m in messages
        if not (
            m.get("role") == "system"
            and isinstance(m.get("content"), str)
            and str(m.get("content")).startswith(LANG_HINT_MARKER)
        )
    ]
    out.append({"role": "system", "content": build_lang_hint(ui_locale)})
    return out


def build_usage_hint(messages: list[dict[str, Any]], context_window: int) -> str:
    """Per-turn context-usage suffix (one volatile line at the very tail).

    Lives in a trailing system message instead of the compact tool description:
    the tools array sits at the head of the provider request, so a per-turn
    description there would invalidate the whole prompt-cache prefix every turn.
    """
    window = context_window if context_window and context_window > 0 else DEFAULT_CONTEXT_WINDOW
    usage = estimate_messages_tokens(messages or [])
    share = round(usage * 100 / window) if window > 0 else 0
    return (
        f"{USAGE_HINT_MARKER} The conversation context is about {usage} of {window} "
        f"tokens (~{share}% used). Weigh this when deciding whether compact_context "
        "is worth a call this turn."
    )


def upsert_usage_hint(
    messages: list[dict[str, Any]], context_window: int
) -> list[dict[str, Any]]:
    """Refresh the trailing context-usage suffix: strip older copies, append one.

    Idempotent across turns (no accumulation in persisted history) and always
    last, so only the suffix itself re-caches.
    """
    out = [
        m for m in messages
        if not (
            m.get("role") == "system"
            and isinstance(m.get("content"), str)
            and str(m.get("content")).startswith(USAGE_HINT_MARKER)
        )
    ]
    out.append({"role": "system", "content": build_usage_hint(out, context_window)})
    return out


async def build_working_context(
    messages: list[dict[str, Any]],
    context_window: int,
    *,
    memory: WorkingMemory,
    llm: Any,
    reply_locale: str | None = None,
    threshold: float | None = None,
    force: bool = False,
    options: CompactionOptions | None = None,
    keep_from: int | None = None,
    provenance: dict[str, Any] | None = None,
    default_focus: str | None = None,
    report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Assemble model context: LLM summary compression + working-memory inject + lang suffix.

    Compress only at the start of each chat turn (may trigger one summary LLM
    call). Persist paths (chat.finalize) use rule-based compression to avoid save latency.
    ``threshold`` (fraction of the context window, e.g. 0.7) comes from the
    user's auto-compact setting; ``None`` keeps the agent-decided default.
    ``force`` (manual ``/compact``) always attempts an LLM summary.
    ``options`` carries intensity/directive/retain; ``keep_from`` pins the
    verbatim cutoff for mid-turn agent-invoked compaction; ``provenance``
    stamps the new summary trailer; ``default_focus`` anchors the summary
    when the run carries no explicit directive; ``report`` collects
    compaction cost (tokens/latency) without raising.
    """
    opts = options or CompactionOptions()
    compacted = await compact_with_summary(
        messages, context_window, memory=memory, llm=llm,
        # The verbatim tail follows the turn policy exactly (retain setting
        # raised by the intensity floor), floored at the latest exchange so
        # the live user message is never summarized away. The platform's
        # keep_recent=20 default must not silently override a smaller retain.
        keep_recent=max(opts.keep_window(), 2),
        threshold=DEFAULT_AUTO_COMPACT_THRESHOLD if threshold is None else threshold,
        force=force,
        options=opts,
        keep_from=keep_from,
        provenance=provenance,
        default_focus=default_focus,
        report=report,
    )
    with_memory = upsert_memory_block(compacted, memory)
    with_lang = upsert_lang_hint(with_memory, reply_locale)
    return upsert_usage_hint(with_lang, context_window)


__all__ = [
    "BREAKDOWN_ASSISTANT",
    "BREAKDOWN_MEMORY",
    "BREAKDOWN_ORDER",
    "BREAKDOWN_OTHER",
    "BREAKDOWN_SYSTEM",
    "BREAKDOWN_THINKING",
    "BREAKDOWN_TOOLS",
    "BREAKDOWN_USER",
    "LANG_HINT_MARKER",
    "LINKED_BLOCK_MARKER",
    "PREP_SYSTEM",
    "REF_BLOCK_MARKER",
    "USAGE_HINT_MARKER",
    "build_context_breakdown",
    "build_lang_hint",
    "build_system_message",
    "build_system_messages",
    "build_usage_hint",
    "build_working_context",
    "format_linked_session",
    "format_linked_sessions",
    "format_memory_index",
    "infer_text_locale",
    "normalize_ui_locale",
    "strip_ref_blocks",
    "upsert_lang_hint",
    "upsert_usage_hint",
]
