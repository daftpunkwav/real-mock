"""Backward-compatible wrapper: the implementation has moved to the ``client`` package.

Preserves the ``from realmock.platform.capabilities.ai.llm.unified_client import UnifiedLLMClient`` path.
"""

from realmock.platform.capabilities.ai.llm.client.unified_client import UnifiedLLMClient

__all__ = ["UnifiedLLMClient"]
