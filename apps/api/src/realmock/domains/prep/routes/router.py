"""Interview-preparation API (route aggregation).

SSE streaming errors return only a redacted user-facing message; the original exception goes to logger.exception.
Content-reading operations (message / stream / messages / fork) require the capability token issued at creation (``X-Interview-Token``).
Owner-level operations (truncate / compact / summary / delete / archive / link /
reissue / purge-empty / purge-all, plus memory writes) require same-origin CSRF
protection but no capability token, so orphans stay manageable.

Handlers live in ``lists.py`` (read-only listing), ``create.py``
(create+cookie), ``chat.py`` (message / stream / messages / context),
``history.py`` (compact / summary / fork / truncate), ``manage.py`` (delete /
purge / archive / link / reissue), and ``memories.py`` (long-term memories).
This module mounts them on the same ``router`` (including their respective
rate-limit dependencies), which ``realmock.domains.prep.router`` mounts with
``prefix="/prep"``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from realmock.domains.prep.routes import chat, create, history, lists, manage, memories
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
    DEFAULT_RATE_LIMIT_PER_MINUTE,
    DEFAULT_SESSION_CREATE_RATE_LIMIT_PER_MINUTE,
)
from realmock.platform.core.ratelimit import rate_limit_dep

if TYPE_CHECKING:
    from fastapi.params import Depends as DependsInstance


def _manage_limit() -> "DependsInstance":
    """Shared rate limit for purge endpoints and memory write endpoints."""
    return Depends(
        rate_limit_dep(key="manage", limit=DEFAULT_RATE_LIMIT_PER_MINUTE),
    )

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
    history.compact_prep_session,
    methods=["POST"],
    response_model=PrepCompactResponse,
    dependencies=[
        Depends(
            rate_limit_dep(
                # Dedicated bucket (not the chat "llm" bucket): the summarizer
                # call is expensive but must not starve normal turns.
                key="compact",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
router.add_api_route(
    "/sessions/{session_id}/summary",
    history.update_prep_summary,
    methods=["PATCH"],
    response_model=PrepCompactResponse,
)
router.add_api_route(
    "/sessions/{session_id}/fork",
    history.fork_prep_session,
    methods=["POST"],
    response_model=PrepForkResponse,
    dependencies=[
        Depends(
            rate_limit_dep(
                key="session_create",
                limit=DEFAULT_SESSION_CREATE_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
router.add_api_route(
    "/sessions/{session_id}/messages/truncate",
    history.truncate_prep_messages,
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
    dependencies=[_manage_limit()],
)
router.add_api_route(
    "/sessions/purge-all",
    manage.purge_all_sessions,
    methods=["POST"],
    dependencies=[_manage_limit()],
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
    dependencies=[_manage_limit()],
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
    dependencies=[_manage_limit()],
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
    dependencies=[_manage_limit()],
)
router.add_api_route(
    "/memories/{memory_id}",
    memories.delete_memory,
    methods=["DELETE"],
    dependencies=[_manage_limit()],
)

__all__ = [
    "router",
]
