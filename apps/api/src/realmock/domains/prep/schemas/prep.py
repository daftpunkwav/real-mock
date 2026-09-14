"""Interview Preparation (Prep) HTTP Contract."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from realmock.platform.core.constants import MAX_USER_TEXT_CHARS


class PrepCreateRequest(BaseModel):
    resume_id: int | None = None
    # Matches PrepSession String(100): longer values 422 here instead of DB error.
    target_role: str = Field(default="", max_length=100)
    target_company: str = Field(default="", max_length=100)


class PrepSessionCreateResponse(BaseModel):
    id: int


class PrepForkResponse(BaseModel):
    id: int
    message_count: int = 0


class PrepSessionSummary(BaseModel):
    id: int
    resume_id: int | None = None
    resume_filename: str | None = None
    summary: str = ""
    message_count: int = 0
    status: str = "active"
    linked_session_id: int | None = None
    token_usage: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    created_at: datetime
    updated_at: datetime


class PrepToolStep(BaseModel):
    name: str = ""
    query: str = ""
    # Call detail for expandable display: public args + the observation the model saw.
    args: dict[str, str] = Field(default_factory=dict)
    result: str = ""


class PrepSearchHit(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""


class PrepSearchGroup(BaseModel):
    query: str = ""
    results: list[PrepSearchHit] = Field(default_factory=list)


class PrepHistoryMessage(BaseModel):
    role: str
    content: str
    steps: list[PrepToolStep] | None = None
    search_groups: list[PrepSearchGroup] | None = None
    thinking: str | None = None
    stopped: bool = False
    # Turn correlation id (persisted on assistant messages; absent on legacy rows).
    turn_id: str | None = None


#: Allowed compaction intensities (shared with the settings UI vocabulary).
COMPACTION_INTENSITIES = ("light", "balanced", "aggressive")

#: Hard bounds for the retain window (frontend clamps too; the API rejects).
RETAIN_MIN = 0
RETAIN_MAX = 200

#: Hard bound for a user-supplied compression directive (frontend truncates too).
DIRECTIVE_MAX_CHARS = 500


class PrepMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=MAX_USER_TEXT_CHARS)
    model_profile_id: int | None = None
    reasoning_effort: str | None = Field(default=None, pattern="^(low|medium|high|max)$")
    # Regenerate support: drop the trailing assistant message before this turn.
    drop_last_assistant: bool = False
    # UI locale for first-turn reply-language context (zh-CN/en; others ignored).
    ui_locale: str | None = None
    # Per-turn # references: session ids whose target + recent turns are
    # injected into this turn only (transient; never persisted, never replaces
    # history). At most 5 are honored; unknown ids resolve to nothing.
    context_session_ids: list[int] | None = Field(default=None, max_length=5)
    # Auto-compact trigger as a fraction of the model's context window
    # (accepted 0.1–0.95; the prep settings UI typically sends 0.5–0.9);
    # None = agent-decided default.
    compact_threshold: float | None = Field(default=None, ge=0.1, le=0.95)
    # Compaction parameters for this turn's auto-compact (intensity/directive/
    # retain from the prep settings UI); absent fields fall back to defaults.
    compact_intensity: str | None = Field(default=None, pattern="^(light|balanced|aggressive)$")
    compact_directive: str | None = Field(default=None, max_length=DIRECTIVE_MAX_CHARS)
    compact_retain: int | None = Field(default=None, ge=RETAIN_MIN, le=RETAIN_MAX)

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        """Reject blank messages: whitespace-only turns waste a full agent round."""
        text = value.strip()
        if not text:
            raise ValueError("content must not be blank")
        return text


class PrepMessageResponse(BaseModel):
    reply: str
    token_usage: int = 0
    # Session-level provider-reported totals (mirrors the stream ``done`` envelope).
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    # Backend-truth persisted length after this turn (client resync source).
    message_count: int = 0
    # Mechanical estimate of this turn's model input (working context incl.
    # per-turn references). Shown with an "estimated" marker when the provider
    # reported no prompt usage for the turn.
    prompt_tokens_estimated: int = 0


class PrepForkRequest(BaseModel):
    # Backend message index to fork through (inclusive); -1 (or any negative)
    # keeps everything. Out-of-range positives clamp to the last message.
    up_to: int = -1


class PrepTruncateRequest(BaseModel):
    # Drop backend messages[from_index:] (retract a user message and all replies after it).
    from_index: int = Field(..., ge=0)
    # Optimistic-concurrency guard: 409 when the persisted history changed
    # since the caller read it (same semantics as compact/summary edits).
    expected_message_count: int | None = Field(default=None, ge=0)


class PrepContextBucket(BaseModel):
    # Stable bucket key: user | assistant | thinking | tools | system | memory | other.
    key: str = ""
    tokens: int = 0


class PrepContextResponse(BaseModel):
    # Measured persisted-history breakdown (mechanical estimate, same ratio as budgeting).
    buckets: list[PrepContextBucket] = Field(default_factory=list)
    total_estimate: int = 0
    # Session-level provider-reported totals (0 when the provider never reported).
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0


class PrepCompactRequest(BaseModel):
    # Manual-compaction parameters (all optional; absent fields resolve from
    # the caller's defaults, e.g. the prep settings UI selections).
    intensity: str | None = Field(default=None, pattern="^(light|balanced|aggressive)$")
    directive: str | None = Field(default=None, max_length=DIRECTIVE_MAX_CHARS)
    retain: int | None = Field(default=None, ge=RETAIN_MIN, le=RETAIN_MAX)
    # False skips the pre-compaction backup fork (summary regeneration reuses
    # the backup taken by the original compaction).
    backup: bool = True
    # Optimistic-concurrency guard: 409 when the persisted history changed
    # since the caller read it (prevents clobbering an in-flight turn).
    expected_message_count: int | None = Field(default=None, ge=0)


class PrepCompactResponse(BaseModel):
    message_count: int = 0
    # True when an LLM summary was written (manual force path, or the over-threshold auto path).
    summarized: bool = False
    estimate_before: int = 0
    estimate_after: int = 0
    # Why the run ended: "summarized" | "nothing_to_fold" | "tool_pairs_only".
    reason: str = ""
    # Full transparency for the compaction card: summary text (provenance
    # trailer stripped), its version, and the pre-compaction fork point.
    summary_text: str = ""
    summary_version: int = 0
    fork_point: int | None = None
    backup_session_id: int | None = None
    # Backend message index where the verbatim tail starts (clients archive
    # everything older for display; null when nothing was folded).
    kept_from: int | None = None
    # Summarizer LLM cost (provider deltas, 0 when no LLM call ran).
    compaction_prompt_tokens: int = 0
    compaction_completion_tokens: int = 0
    compaction_latency_ms: float = 0.0


class PrepSummaryUpdateRequest(BaseModel):
    # Edited summary text (provenance trailer is managed server-side).
    text: str = Field(..., min_length=1, max_length=8000)
    expected_message_count: int | None = Field(default=None, ge=0)


class PrepArchiveRequest(BaseModel):
    archived: bool = True


class PrepPurgeAllRequest(BaseModel):
    # Explicit confirmation for the irreversible purge-all operation;
    # requests without confirm=True are rejected (A0001).
    confirm: bool = False


class PrepLinkRequest(BaseModel):
    # Link another session into this one's context; null unlinks.
    linked_session_id: int | None = None


# --- Long-term memories ---

#: Allowed memory origins: explicit user rating, user-emphasized fact, agent note.
MEMORY_ORIGINS = frozenset({"user_rating", "user_emphasis", "agent_note"})


class PrepMemoryCreate(BaseModel):
    session_id: int | None = None
    user_input: str = Field(default="", max_length=8000)
    agent_output: str = Field(default="", max_length=8000)
    score: int | None = Field(default=None, ge=1, le=10)
    reasons: list[str] = Field(default_factory=list, max_length=10)
    comment: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    origin: str = Field(default="user_rating", pattern="^(user_rating|user_emphasis|agent_note)$")


class PrepMemorySummary(BaseModel):
    id: int
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    origin: str = ""
    score: int | None = None
    session_id: int | None = None
    updated_at: datetime


class PrepMemoryDetail(PrepMemorySummary):
    user_input: str = ""
    agent_output: str = ""
    comment: str = ""
    reasons: list[str] = Field(default_factory=list)
    created_at: datetime


class PrepMemoryUpdate(BaseModel):
    summary: str | None = Field(default=None, max_length=200)
    tags: list[str] | None = Field(default=None, max_length=20)
    comment: str | None = Field(default=None, max_length=2000)
    score: int | None = Field(default=None, ge=1, le=10)


class PrepMemoryBatchDelete(BaseModel):
    ids: list[int] = Field(default_factory=list, min_length=1, max_length=100)


__all__ = [
    "COMPACTION_INTENSITIES",
    "DIRECTIVE_MAX_CHARS",
    "MEMORY_ORIGINS",
    "RETAIN_MAX",
    "RETAIN_MIN",
    "PrepArchiveRequest",
    "PrepCompactRequest",
    "PrepCompactResponse",
    "PrepContextBucket",
    "PrepContextResponse",
    "PrepCreateRequest",
    "PrepForkRequest",
    "PrepForkResponse",
    "PrepHistoryMessage",
    "PrepLinkRequest",
    "PrepMemoryBatchDelete",
    "PrepMemoryCreate",
    "PrepMemoryDetail",
    "PrepMemorySummary",
    "PrepMemoryUpdate",
    "PrepMessageRequest",
    "PrepMessageResponse",
    "PrepPurgeAllRequest",
    "PrepSessionCreateResponse",
    "PrepSessionSummary",
    "PrepSummaryUpdateRequest",
    "PrepTruncateRequest",
]
