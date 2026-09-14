"""LLM client package.

Maintains backward-compatible import paths:

- ``from realmock.platform.capabilities.ai.llm.client import LLMClient`` (formerly ``client.py``)
- ``from realmock.platform.capabilities.ai.llm.unified_client import UnifiedLLMClient`` (formerly ``unified_client.py``)
- ``from realmock.platform.capabilities.ai.llm.tool_args import parse_tool_arguments`` (formerly ``tool_args.py``)

Split submodules:

- :mod:`base` — retries, text extraction, and environment-check helpers
- :mod:`llm_client` — OpenAI-compatible BYOK client
- :mod:`unified_client` — unified multi-protocol client
- :mod:`tool_args` — function-calling tool-argument parsing
"""

from .llm_client import LLMClient
from .tool_args import parse_tool_arguments
from .unified_client import UnifiedLLMClient

__all__ = ["LLMClient", "UnifiedLLMClient", "parse_tool_arguments"]
