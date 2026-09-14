"""First-turn system seed: pinned instructions + resume/profile/company + memories/linked tail.

Cache layout (prefix-stable for prompt caching): the seed is a run of system
messages ordered stable-first — [pinned instructions] [resume/profile/company]
[memories/linked] — so volatile tail blocks invalidate only their own suffix.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from realmock.domains.prep.agents.context.linked import format_linked_session
from realmock.domains.prep.services import list_memories
from realmock.platform.catalogs.company import get_company_context
from realmock.platform.core.prompts import with_agent_output_rules
from realmock.platform.database import api_db_session, sessions_db_session
from realmock.platform.services.candidate_read import format_profile_summary, format_resume_summary

# Long-term memories injected into the system prompt (index only; details on demand).
_MEMORY_INDEX_LIMIT = 10
_MEMORY_SUMMARY_CHARS = 120

PREP_SYSTEM = with_agent_output_rules("""You are the interview-prep coach in this mock-interview system. Help the user prepare for their target role using the **selected resume**.

Match the user's language in your replies AND in your <think> reasoning (do not force a UI locale).

How you work (think-then-act loop):
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


def format_memory_index(db: Session | None = None) -> str:
    """Render the long-term memory index block for the system prompt (never raises).

    Args:
        db: Optional live sessions Session to reuse (seed path passes its own
            session to avoid opening a second connection). When None, a short
            session is opened internally for standalone callers.
    """
    if db is None:
        try:
            with sessions_db_session() as owned:
                return format_memory_index(owned)
        except Exception:
            return ""
    try:
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
    memories = format_memory_index(db)
    linked = format_linked_session(db, linked_session_id)
    context_block = "\n".join(part for part in (company, ctx, profile) if part)
    tail_block = "\n".join(part for part in (memories, linked) if part)
    return [PREP_SYSTEM, context_block, tail_block]


__all__ = [
    "PREP_SYSTEM",
    "build_system_message",
    "build_system_messages",
    "format_memory_index",
]
