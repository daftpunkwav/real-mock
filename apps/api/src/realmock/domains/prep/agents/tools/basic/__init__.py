"""Basic coaching tools: one file per tool, assembled as BASIC_SPECS."""

from __future__ import annotations

from realmock.domains.prep.agents.tools.basic.code_exec import CODE_EXEC_SPEC
from realmock.domains.prep.agents.tools.basic.company_info import COMPANY_INFO_SPEC
from realmock.domains.prep.agents.tools.basic.quiz import QUIZ_SPEC
from realmock.domains.prep.agents.tools.basic.take_note import TAKE_NOTE_SPEC
from realmock.domains.prep.agents.tools.basic.web_fetch import WEB_FETCH_SPEC
from realmock.domains.prep.agents.tools.basic.web_search import WEB_SEARCH_SPEC

BASIC_SPECS = [
    WEB_SEARCH_SPEC,
    WEB_FETCH_SPEC,
    COMPANY_INFO_SPEC,
    CODE_EXEC_SPEC,
    QUIZ_SPEC,
    TAKE_NOTE_SPEC,
]


__all__ = [
    "BASIC_SPECS",
    "CODE_EXEC_SPEC",
    "COMPANY_INFO_SPEC",
    "QUIZ_SPEC",
    "TAKE_NOTE_SPEC",
    "WEB_FETCH_SPEC",
    "WEB_SEARCH_SPEC",
]
