"""Long-term memory tools: one file per tool, assembled as MEMORY_SPECS."""

from __future__ import annotations

from realmock.domains.prep.agents.tools.memory.get_detail import MEMORY_GET_DETAIL_SPEC
from realmock.domains.prep.agents.tools.memory.list_summaries import MEMORY_LIST_SUMMARIES_SPEC
from realmock.domains.prep.agents.tools.memory.list_tags import MEMORY_LIST_TAGS_SPEC
from realmock.domains.prep.agents.tools.memory.write import MEMORY_WRITE_SPEC

MEMORY_SPECS = [
    MEMORY_LIST_TAGS_SPEC,
    MEMORY_LIST_SUMMARIES_SPEC,
    MEMORY_GET_DETAIL_SPEC,
    MEMORY_WRITE_SPEC,
]


__all__ = [
    "MEMORY_GET_DETAIL_SPEC",
    "MEMORY_LIST_SUMMARIES_SPEC",
    "MEMORY_LIST_TAGS_SPEC",
    "MEMORY_SPECS",
    "MEMORY_WRITE_SPEC",
]
