"""Payload contract tests for realmock.platform.contracts.

Covers: default field values for interview-finished and report-summary payloads.
Conventions: pure dataclass construction; no I/O.
"""

from __future__ import annotations


class TestContractsPayloads:
    def test_payload_models(self) -> None:
        from realmock.platform.contracts import InterviewFinishedPayload, ReportSummaryPayload

        assert InterviewFinishedPayload(session_id=1).workflow_type == "technical"
        assert ReportSummaryPayload(session_id=2).weaknesses == []
