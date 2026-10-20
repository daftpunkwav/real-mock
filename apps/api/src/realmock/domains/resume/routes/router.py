"""Resume HTTP route aggregation.

Handlers live in ``upload`` / ``crud`` / ``file`` / ``analyze``. This module
mounts them on one ``router`` (including rate-limit dependencies) which
``domains.resume.router`` then prefixes with ``/resume``.

Import-time ``contract_guard`` fails fast if catalog / ORM / response drifted.
Must not import persistence or interpret field lengths.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response, StreamingResponse

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
from realmock.domains.resume.routes.export import export_analysis
from realmock.domains.resume.routes.file import (
    get_resume_file,
    get_resume_page_image,
    get_resume_pages_meta,
)
from realmock.domains.resume.routes.parse_retry import retry_resume_parse
from realmock.domains.resume.routes.upload import upload_resume, upload_resume_version
from realmock.domains.resume.schemas import (
    ResumeAnalysesClearResponse,
    ResumeAnalysis,
    ResumeCollectionDeleteResponse,
    ResumeDeleteResponse,
    ResumeDomainLimits,
    ResumePagesMetaResponse,
    ResumeResponse,
)
from realmock.domains.resume.schemas.limits import FILE_DOWNLOAD_MEDIA_TYPES
from realmock.domains.resume.services import contract_guard
from realmock.platform.contracts.data_export import DataExportFile
from realmock.platform.core.constants import (
    DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
    DEFAULT_RATE_LIMIT_PER_MINUTE,
    RESUME_PAGE_RATE_LIMIT_PER_MINUTE,
)
from realmock.platform.core.ratelimit import rate_limit_dep

# Import-time guard: catalog / ORM / response must stay aligned.
contract_guard.assert_resume_contract_aligned()

# OpenAPI content map of the original-file download: every media type the
# route can answer with, text formats as plain strings and binary formats as
# binary payloads.
_FILE_DOWNLOAD_CONTENT: dict[str, dict[str, dict[str, str]]] = {
    media_type: {
        "schema": (
            {"type": "string"}
            if media_type.startswith("text/")
            else {"type": "string", "format": "binary"}
        )
    }
    for media_type in FILE_DOWNLOAD_MEDIA_TYPES
}

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
    response_model=ResumeAnalysesClearResponse,
)
router.add_api_route(
    "/{resume_id}/analysis-export",
    export_analysis,
    methods=["GET"],
    response_model=DataExportFile,
)
router.add_api_route(
    "/collection",
    delete_all_resumes,
    methods=["DELETE"],
    response_model=ResumeCollectionDeleteResponse,
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
    response_class=FileResponse,
    responses={200: {"content": _FILE_DOWNLOAD_CONTENT}},
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
    response_model=ResumePagesMetaResponse,
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
    response_class=Response,
    responses={200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}}},
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
    response_model=ResumeDeleteResponse,
)
router.add_api_route(
    "/{resume_id}/analyze/stream",
    analyze_resume_stream,
    methods=["POST"],
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
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
