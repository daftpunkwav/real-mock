"""GitHub tool layer (MCP style): lets the interviewer verify candidate repositories in real time.

Design notes:
- Uses the GitHub REST API, with optional ``GITHUB_TOKEN`` for higher limits;
- Tool signatures align with the MCP ``github`` server semantics, simplifying a future switch to official MCP transport;
- All calls have timeouts and graceful failure handling, without disrupting the main interview flow.
"""

from realmock.platform.capabilities.integrations.github.client import GitHubClient
from realmock.platform.capabilities.integrations.github.tools import (
    GITHUB_TOOL_DEFINITIONS,
    execute_github_tool,
)

__all__ = [
    "GitHubClient",
    "GITHUB_TOOL_DEFINITIONS",
    "execute_github_tool",
]
