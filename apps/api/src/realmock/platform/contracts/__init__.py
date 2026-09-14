"""Platform cross-domain contracts (DTOs, ports, lifecycle hooks).

Domains must not import each other. Composition root wires implementations
into these contracts; consumers depend only on this package.
"""

from __future__ import annotations

from realmock.platform.contracts.interview_finished import InterviewFinishedPayload
from realmock.platform.contracts.lifecycle_hooks import (
    get_system_insights_provider,
    notify_interview_finished,
    notify_report_summary,
    set_on_interview_finished,
    set_on_report_summary,
    set_system_insights_provider,
)
from realmock.platform.contracts.report_summary import ReportSummaryPayload
from realmock.platform.contracts.session_catalog import (
    SessionCatalogItem,
    SessionCatalogPort,
    SessionListItem,
    SessionSnapshot,
    get_session_catalog,
    register_session_catalog,
    set_session_catalog,
    snapshot_from_catalog_dict,
)
from realmock.platform.contracts.session_score import (
    SessionScoreProjectionPort,
    apply_session_overall_score,
    get_session_score_projection,
    register_session_score_projection,
)

__all__ = [
    "InterviewFinishedPayload",
    "ReportSummaryPayload",
    "SessionCatalogItem",
    "SessionCatalogPort",
    "SessionListItem",
    "SessionScoreProjectionPort",
    "SessionSnapshot",
    "apply_session_overall_score",
    "get_session_catalog",
    "get_session_score_projection",
    "get_system_insights_provider",
    "notify_interview_finished",
    "notify_report_summary",
    "register_session_catalog",
    "register_session_score_projection",
    "set_on_interview_finished",
    "set_on_report_summary",
    "set_session_catalog",
    "set_system_insights_provider",
    "snapshot_from_catalog_dict",
]
