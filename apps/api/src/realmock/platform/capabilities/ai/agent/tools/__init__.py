"""Agent tool package: reusable GitHub / search / profile / resume specs.

Process/plan tools stay in the resume domain. This package must not import
FastAPI or resume/prep/interview agents.
"""

from .codeexec import (
    CodeResult,
    format_observation,
    run_code_snippet,
)
from .executor import invoke_with_timeout
from .fetch import (
    FETCH_DEFAULT_MAX_CHARS,
    FETCH_HARD_MAX_CHARS,
    execute_web_fetch,
    web_fetch_tool_spec,
)
from .github import github_tool_specs
from .profile import ProfileSnapshot, profile_from_orm, profile_tool_specs
from .resume import ResumeSnapshot, resume_tool_specs, snapshot_from_payload
from .search import (
    SEARCH_DEFAULT_MAX_RESULTS,
    SEARCH_HARD_MAX_RESULTS,
    execute_web_search,
    search_tool_spec,
)
from .spec import ToolBundle, ToolSpec, openai_tool

__all__ = [
    "FETCH_DEFAULT_MAX_CHARS",
    "FETCH_HARD_MAX_CHARS",
    "SEARCH_DEFAULT_MAX_RESULTS",
    "SEARCH_HARD_MAX_RESULTS",
    "CodeResult",
    "ProfileSnapshot",
    "ResumeSnapshot",
    "ToolBundle",
    "ToolSpec",
    "execute_web_fetch",
    "execute_web_search",
    "format_observation",
    "github_tool_specs",
    "invoke_with_timeout",
    "openai_tool",
    "profile_from_orm",
    "profile_tool_specs",
    "resume_tool_specs",
    "run_code_snippet",
    "search_tool_spec",
    "web_fetch_tool_spec",
    "snapshot_from_payload",
]
