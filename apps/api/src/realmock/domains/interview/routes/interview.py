"""Interview-session API (route aggregation).

Handlers for session CRUD and turn start/message/finish are defined in ``sessions.py`` /
``turns.py`` respectively; this module only mounts them on the same ``router`` (including their
respective rate limits and local-peer dependencies), while keeping ``start_interview`` /
``send_message`` importable from this module.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from realmock.platform.core.constants import (
    DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
    DEFAULT_SESSION_CREATE_RATE_LIMIT_PER_MINUTE,
)
from realmock.platform.core.ratelimit import rate_limit_dep
from realmock.platform.schemas import ResumePickerItem
# Direct submodule imports to avoid clashing with routes.__init__; no cycle.
from realmock.domains.interview.routes.processes import (
    create_process,
    create_round,
    get_process,
    list_process_routes,
)
from realmock.domains.interview.routes.sessions import (
    InterviewSessionResponse,
    create_session,
    get_messages,
    get_session,
    list_resume_picker,
    list_sessions,
)
from realmock.domains.interview.routes.turns import (
    FinishInterviewResponse,
    InterviewMessageResponse,
    finish_interview,
    send_message,
    start_interview,
)
from realmock.domains.interview.schemas.process import (
    InterviewProcessResponse,
    ProcessCreatedResponse,
)

router = APIRouter()

router.add_api_route(
    "/resumes",
    list_resume_picker,
    methods=["GET"],
    response_model=list[ResumePickerItem],
)
router.add_api_route(
    "/processes",
    create_process,
    methods=["POST"],
    response_model=ProcessCreatedResponse,
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
    "/processes",
    list_process_routes,
    methods=["GET"],
    response_model=list[InterviewProcessResponse],
)
router.add_api_route(
    "/processes/{process_id}",
    get_process,
    methods=["GET"],
    response_model=InterviewProcessResponse,
)
router.add_api_route(
    "/processes/{process_id}/rounds",
    create_round,
    methods=["POST"],
    response_model=InterviewSessionResponse,
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
    "/sessions",
    create_session,
    methods=["POST"],
    response_model=InterviewSessionResponse,
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
    "/sessions",
    list_sessions,
    methods=["GET"],
    response_model=list[InterviewSessionResponse],
)
router.add_api_route(
    "/sessions/{session_id}",
    get_session,
    methods=["GET"],
    response_model=InterviewSessionResponse,
)
router.add_api_route(
    "/sessions/{session_id}/messages",
    get_messages,
    methods=["GET"],
)
router.add_api_route(
    "/sessions/{session_id}/start",
    start_interview,
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
    "/sessions/{session_id}/message",
    send_message,
    methods=["POST"],
    response_model=InterviewMessageResponse,
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
    "/sessions/{session_id}/finish",
    finish_interview,
    methods=["POST"],
    response_model=FinishInterviewResponse,
    dependencies=[
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
# start_interview / send_message are top-level named imports, preserving re-export compatibility
