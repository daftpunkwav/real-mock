"""Interview-preparation API (route aggregation).

SSE streaming errors return only a redacted user-facing message; the original exception goes to logger.exception.
Content-reading operations (message / stream / messages / fork) require the capability token issued at creation (``X-Interview-Token``).
Management operations (truncate / delete / archive / link / purge-empty) are owner-level: same-origin CSRF only, no token.

Handlers for read-only listing / create+cookie / session chat are defined in
``lists.py`` / ``create.py`` / ``chat.py`` respectively, long-term memories in
``memories.py``. This module
mounts them on the same ``router`` (including their respective rate-limit dependencies), which
``realmock.domains.prep.router`` mounts with ``prefix="/prep"``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from realmock.domains.prep.routes import chat, create, lists, manage, memories
from realmock.domains.prep.schemas import (
    PrepCompactResponse,
    PrepContextResponse,
    PrepForkResponse,
    PrepHistoryMessage,
    PrepMemoryDetail,
    PrepMemorySummary,
    PrepMessageResponse,
    PrepSessionCreateResponse,
    PrepSessionSummary,
    ResumePickerItem,
)
from realmock.platform.core.constants import (
    DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
    DEFAULT_SESSION_CREATE_RATE_LIMIT_PER_MINUTE,
)
from realmock.platform.core.ratelimit import rate_limit_dep

router = APIRouter()

router.add_api_route(
    "/resumes",
    lists.list_resume_picker,
    methods=["GET"],
    response_model=list[ResumePickerItem],
)
router.add_api_route(
    "/sessions",
    lists.list_prep_sessions,
    methods=["GET"],
    response_model=list[PrepSessionSummary],
)
router.add_api_route(
    "/sessions",
    create.create_prep_session,
    methods=["POST"],
    response_model=PrepSessionCreateResponse,
    dependencies=[
        Depends(
            rate_limit_dep(
                key="session_create",
                limit=DEFAULT_SESSION_CREATE_RATE_LIMIT_PER_MINUTE,
            )
        ),
    ],
)
router.add_api_route(
    "/sessions/{session_id}/message",
    chat.prep_message,
    methods=["POST"],
    response_model=PrepMessageResponse,
    dependencies=[
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
router.add_api_route(
    "/sessions/{session_id}/message/stream",
    chat.prep_message_stream,
    methods=["POST"],
    dependencies=[
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
router.add_api_route(
    "/sessions/{session_id}/messages",
    chat.get_prep_messages,
    methods=["GET"],
    response_model=list[PrepHistoryMessage],
)
router.add_api_route(
    "/sessions/{session_id}/context",
    chat.get_prep_context,
    methods=["GET"],
    response_model=PrepContextResponse,
)
router.add_api_route(
    "/sessions/{session_id}/compact",
    chat.compact_prep_session,
    methods=["POST"],
    response_model=PrepCompactResponse,
)
router.add_api_route(
    "/sessions/{session_id}/summary",
    chat.update_prep_summary,
    methods=["PATCH"],
    response_model=PrepCompactResponse,
)
router.add_api_route(
    "/sessions/{session_id}/fork",
    chat.fork_prep_session,
    methods=["POST"],
    response_model=PrepForkResponse,
)
router.add_api_route(
    "/sessions/{session_id}/messages/truncate",
    chat.truncate_prep_messages,
    methods=["POST"],
)
router.add_api_route(
    "/sessions/{session_id}",
    manage.delete_prep_session,
    methods=["DELETE"],
)
router.add_api_route(
    "/sessions/purge-empty",
    manage.purge_empty_sessions,
    methods=["POST"],
)
router.add_api_route(
    "/sessions/purge-all",
    manage.purge_all_sessions,
    methods=["POST"],
)
router.add_api_route(
    "/sessions/{session_id}/archive",
    manage.archive_prep_session,
    methods=["PATCH"],
)
router.add_api_route(
    "/sessions/{session_id}/link",
    manage.link_prep_session,
    methods=["PUT"],
)
router.add_api_route(
    "/sessions/{session_id}/reissue",
    manage.reissue_prep_token,
    methods=["POST"],
    response_model=PrepSessionCreateResponse,
)
router.add_api_route(
    "/memories",
    memories.create_memory_from_rating,
    methods=["POST"],
    response_model=PrepMemoryDetail,
)
router.add_api_route(
    "/memories",
    memories.list_memory_summaries,
    methods=["GET"],
    response_model=list[PrepMemorySummary],
)
router.add_api_route(
    "/memories/tags",
    memories.list_memory_tags,
    methods=["GET"],
)
router.add_api_route(
    "/memories/batch-delete",
    memories.batch_delete_memories,
    methods=["POST"],
)
router.add_api_route(
    "/memories/{memory_id}",
    memories.get_memory_detail,
    methods=["GET"],
    response_model=PrepMemoryDetail,
)
router.add_api_route(
    "/memories/{memory_id}",
    memories.update_memory,
    methods=["PATCH"],
    response_model=PrepMemoryDetail,
)
router.add_api_route(
    "/memories/{memory_id}",
    memories.delete_memory,
    methods=["DELETE"],
)
