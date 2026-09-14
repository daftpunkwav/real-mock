"""Global protocol constants.

Centralizes string literals used by frontend/backend contracts so that:

- Frontend ``src/config/*.ts`` files correspond one-to-one with this backend module;
- Editors can locate every reference during renaming / protocol evolution;
- ``"foo"`` values are not scattered across dozens of files.

Interview-specific enums (phase / workflow / persona style / follow-up category / WebSocket event) have moved down to
``realmock.domains.interview.constants``; this module retains only platform constants genuinely shared by all services/domains.

Before changing any constant, update both locations and submit them in one atomic commit.
"""

from __future__ import annotations

from enum import StrEnum


# ── LLM Protocol ────────────────────────────────────────


class LLMProtocol(StrEnum):
    OPENAI_CHAT = "openai_chat"
    ANTHROPIC_MESSAGES = "anthropic_messages"
    OPENAI_RESPONSES = "openai_responses"


DEFAULT_LLM_PROTOCOL = LLMProtocol.OPENAI_CHAT

# Token-budget fallbacks when a model profile lacks context_window / max_output.
# Lives here (not in capabilities) so config / models / schemas / services can
# import them without a reverse edge into the capabilities package.
DEFAULT_CONTEXT_WINDOW = 256_000
DEFAULT_MAX_OUTPUT_TOKENS = 64_000


# Three processor stage identifiers
class PipelineStage(StrEnum):
    RECOGNIZE = "recognize"
    REASON = "reason"
    SPEAK = "speak"


# ── RAG Backends ────────────────────────────────────────


class RAGBackendKind(StrEnum):
    """LOCAL RAG backend (RAGBackendKind.LOCAL) using local Chroma + OpenAI-compatible ``/embeddings``.

Applicable to every LLM provider that exposes an OpenAI-compatible ``/embeddings`` endpoint
(OpenAI / DeepSeek / SiliconFlow / Moonshot / GLM / other compatible providers).

Implementation notes:

- Persistence directory under ``realmock/platform/`` (see module body).
    """

    LOCAL = "local"
    STEPFUN = "stepfun"
    NONE = "none"


DEFAULT_RAG_BACKEND = RAGBackendKind.LOCAL


# ── Session status ──────────────────────────────────────


class SessionStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    # Hidden from the default list but still fully usable (prep session archive).
    ARCHIVED = "archived"


# ── SSE Events ────────────────────────────────────────


class SSEMessageType(StrEnum):
    TOKEN = "token"
    DONE = "done"
    ERROR = "error"


# ── Rate Limit ──────────────────────────────────────

DEFAULT_RATE_LIMIT_PER_MINUTE = 60
DEFAULT_LLM_RATE_LIMIT_PER_MINUTE = 10
# Resume page rendering (preview page turning): one N page view = 1 dimensional information + N page image requests,
# The upper limit is 120/min, ensuring that dozens of pages of resumes can be read completely
RESUME_PAGE_RATE_LIMIT_PER_MINUTE = 120
# Interview/coaching session creation: Prevent batch creation of LAN sessions from burning quotas
DEFAULT_SESSION_CREATE_RATE_LIMIT_PER_MINUTE = 20

# HTTP/WS user text limit (characters)
MAX_USER_TEXT_CHARS = 16_000
MAX_CONFIG_STR_CHARS = 200


# ── HTTP Headers / Security ────────────────────────────────────────

API_KEY_ENCRYPTION_VERSION = "enc:v2"
TRACE_ID_HEADER = "X-Trace-Id"


# ──Resume analysis──────────────────────────────────────

RESUME_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
# Do not accept .doc: the parsing pipeline (python-docx) recognizes only ZIP containers, so legacy OLE files will always fail to parse even if accepted
RESUME_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "docx", "md", "txt"})


# ── WebSocket / Interview Runtime ────────────────────────────────────────

HEARTBEAT_TIMEOUT_SEC = 30.0
HEARTBEAT_MAX_MISSES = 3
AUDIO_BUFFER_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
TTS_QUEUE_MAX_SIZE = 50
