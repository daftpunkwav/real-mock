"""Backward-compatible wrapper: the implementation has moved to the ``client`` package.

Preserves the ``from realmock.platform.capabilities.ai.llm.tool_args import parse_tool_arguments`` path.
"""

from realmock.platform.capabilities.ai.llm.client.tool_args import parse_tool_arguments

__all__ = ["parse_tool_arguments"]
