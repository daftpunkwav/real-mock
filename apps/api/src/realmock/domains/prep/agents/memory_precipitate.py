"""End-of-turn memory precipitation: one advisory LLM call, write only on verdict.

After a turn finalizes, a single cheap call asks whether the turn produced a
durable fact worth keeping (target direction, confirmed weak spot, style
preference). Nothing is written unconditionally — the model decides, mirroring
the ``memory_write`` tool's semantics. Every failure is swallowed (logged):
precipitation is an enhancement, never a turn blocker.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from realmock.domains.prep.services import list_memories
from realmock.platform.core.prompts import strip_emojis
from realmock.platform.database import sessions_db_session

if TYPE_CHECKING:
    from .agent import PrepAgent

from .tools.memory.write import run_memory_write

logger = logging.getLogger(__name__)

# Bound the prompt: the turn digest and the existing memory index stay small.
_TURN_DIGEST_CHARS = 1500
_ANSWER_DIGEST_CHARS = 2500

_PRECIPITATE_PROMPT = """You are the memory curator of an interview-prep coaching agent. Review the finished turn and decide whether EXACTLY ONE durable long-term memory should be saved.

Worth saving: durable user facts and preferences — confirmed target role/company/direction, newly revealed weak spots, explicit coaching-style preferences, hard constraints (deadlines, tech stack).
NOT worth saving: this turn's Q&A content itself, transient moods, anything the coach already knew from the resume/profile, small talk, or turns with no clear conclusion.

Existing memory index (do not duplicate these topics):
{memory_index}

Finished turn:
User asked: {user_text}
Coach answered (digest): {answer_digest}

Reply with ONLY a JSON object:
{{"save": false}}
or
{{"save": true, "summary": "<one line ≤200 chars, topic-organized>", "user_input": "<the durable user statement, ≤500 chars>", "agent_output": "<the durable conclusion, ≤500 chars>", "tags": ["tag1", "tag2"], "origin": "agent_note"}}"""


async def precipitate_turn_memory(
    agent: "PrepAgent", user_text: str, final: str
) -> None:
    """Ask once whether the finished turn is worth remembering; write at most one memory.

    Never raises: the user already has their answer, so any failure here must
    not surface. Runs as a detached task after the turn completes — it must
    own everything it touches (the LLM client opens a per-call HTTP session;
    DB reads open their own sessions.db connection). The provider usage of
    this advisory call is deliberately not counted in session totals.
    """
    try:
        if len((final or "").strip()) < 80:
            return  # Too little substance to curate.
        try:
            with sessions_db_session() as db:
                rows = list_memories(db, limit=10)
        except Exception:
            rows = []
        memory_index = "; ".join(
            f"#{row.id} {str(row.summary or '')[:80]}" for row in rows
        )
        answer_digest = (final or "").strip()[:_ANSWER_DIGEST_CHARS]
        prompt = _PRECIPITATE_PROMPT.format(
            memory_index=memory_index or "(empty)",
            user_text=(user_text or "").strip()[:_TURN_DIGEST_CHARS],
            answer_digest=answer_digest,
        )
        verdict: dict[str, Any] = await agent.llm.chat_json(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=400,
        )
        if not isinstance(verdict, dict) or verdict.get("save") is not True:
            return
        summary = strip_emojis(str(verdict.get("summary") or "")).strip()
        if not summary:
            return
        args = {
            "summary": summary[:200],
            "user_input": strip_emojis(str(verdict.get("user_input") or ""))[:500],
            "agent_output": strip_emojis(str(verdict.get("agent_output") or ""))[:500],
            "tags": [str(t)[:30] for t in (verdict.get("tags") or [])[:5] if isinstance(t, (str, int))],
            "origin": "agent_note",
            # The key only dedupes accidental double-writes within one turn
            # (each turn mints a fresh turn_id). Regenerated turns are covered
            # by run_memory_write's exact-summary dedupe instead.
            "idempotency_key": f"precipitate:{agent.last_turn_id}",
        }
        observation, _ = await run_memory_write(args, agent.memory)
        logger.info("Prep turn memory precipitation: %s", observation[:160])
    except Exception as exc:
        logger.warning("Prep turn memory precipitation skipped: %s", exc)



__all__ = ["precipitate_turn_memory"]
