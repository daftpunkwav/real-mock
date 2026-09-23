"""Resume HTTP route aggregation.

Handlers live in ``upload`` / ``crud`` / ``file`` / ``analyze``. This module
mounts them on one ``router`` (including rate-limit dependencies) which
``domains.resume.router`` then prefixes with ``/resume``.

Import-time ``contract_guard`` fails fast if catalog / ORM / response drifted.
Must not import persistence or interpret field lengths.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from realmock.domains.resume.routes.analyze import analyze_resume, analyze_resume_stream
from realmock.domains.resume.routes.crud import (
    activate_resume,
    clear_review_results,
    delete_all_resumes,
    delete_resume,
    get_resume,
    get_resume_limits,
    list_resumes,
)
from realmock.domains.resume.routes.file import (
    get_resume_file,
    get_resume_page_image,
    get_resume_pages_meta,
)
from realmock.domains.resume.routes.parse_retry import retry_resume_parse
from realmock.domains.resume.routes.upload import upload_resume, upload_resume_version
from realmock.domains.resume.schemas import ResumeAnalysis, ResumeDomainLimits, ResumeResponse
from realmock.domains.resume.services import contract_guard
from realmock.platform.core.constants import (
    DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
    DEFAULT_RATE_LIMIT_PER_MINUTE,
    RESUME_PAGE_RATE_LIMIT_PER_MINUTE,
)
from realmock.platform.core.ratelimit import rate_limit_dep

# Import-time guard: catalog / ORM / response must stay aligned.
contract_guard.assert_resume_contract_aligned()

router = APIRouter()

router.add_api_route(
    "/upload",
    upload_resume,
    methods=["POST"],
    response_model=ResumeResponse,
    dependencies=[
        Depends(
            rate_limit_dep(
                key="upload",
                limit=DEFAULT_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
router.add_api_route(
    "/limits",
    get_resume_limits,
    methods=["GET"],
    response_model=ResumeDomainLimits,
)
router.add_api_route(
    "/list",
    list_resumes,
    methods=["GET"],
    response_model=list[ResumeResponse],
)
router.add_api_route(
    "/analyses",
    clear_review_results,
    methods=["DELETE"],
)
router.add_api_route(
    "/collection",
    delete_all_resumes,
    methods=["DELETE"],
)
router.add_api_route(
    "/{resume_id}",
    get_resume,
    methods=["GET"],
    response_model=ResumeResponse,
)
router.add_api_route(
    "/{resume_id}/file",
    get_resume_file,
    methods=["GET"],
    dependencies=[
        Depends(
            rate_limit_dep(
                key="resume_file",
                limit=DEFAULT_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
router.add_api_route(
    "/{resume_id}/pages",
    get_resume_pages_meta,
    methods=["GET"],
    dependencies=[
        Depends(
            rate_limit_dep(
                key="resume_page",
                limit=RESUME_PAGE_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
router.add_api_route(
    "/{resume_id}/pages/{page_no}",
    get_resume_page_image,
    methods=["GET"],
    dependencies=[
        Depends(
            rate_limit_dep(
                key="resume_page",
                limit=RESUME_PAGE_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
router.add_api_route(
    "/{resume_id}/versions",
    upload_resume_version,
    methods=["POST"],
    response_model=ResumeResponse,
    dependencies=[
        Depends(
            rate_limit_dep(
                key="upload",
                limit=DEFAULT_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
router.add_api_route(
    "/{resume_id}/parse",
    retry_resume_parse,
    methods=["POST"],
    response_model=ResumeResponse,
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
    "/{resume_id}/activate",
    activate_resume,
    methods=["POST"],
    response_model=ResumeResponse,
)
router.add_api_route(
    "/{resume_id}",
    delete_resume,
    methods=["DELETE"],
)
router.add_api_route(
    "/{resume_id}/analyze/stream",
    analyze_resume_stream,
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
    "/{resume_id}/analyze",
    analyze_resume,
    methods=["POST"],
    response_model=ResumeAnalysis,
    dependencies=[
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
