"""LLM client package.

Public surface re-exported from submodules so the established import
paths keep working:

- ``LLMClient`` — OpenAI-compatible BYOK client (:mod:`llm_client`)
- ``UnifiedLLMClient`` — unified multi-protocol client (:mod:`unified_client`)
- ``parse_tool_arguments`` — function-calling tool-argument parsing (:mod:`tool_args`)

:mod:`base` holds the shared retry, text-extraction, and environment-check
helpers.
"""

from .llm_client import LLMClient
from .tool_args import parse_tool_arguments
from .unified_client import UnifiedLLMClient

__all__ = ["LLMClient", "UnifiedLLMClient", "parse_tool_arguments"]
