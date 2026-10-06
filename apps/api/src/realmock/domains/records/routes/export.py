"""Export routes: download one session's report or raw record (md / json)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from realmock.domains.records.services import export as export_service
from realmock.platform.contracts.data_export import DataExportFile
from realmock.platform.core.session_auth import extract_token
from realmock.platform.database import get_sessions_db

router = APIRouter()

ExportFormat = Literal["md", "json"]


@router.get("/export/report/{session_id}", response_model=DataExportFile)
def export_report(
    session_id: int,
    export_format: ExportFormat = Query(default="md", alias="format"),
    db: Session = Depends(get_sessions_db),
    access: str | None = Depends(extract_token),
):
    """Download the debrief report for one session (finished sessions only)."""
    if export_format == "json":
        return export_service.build_report_export_json(db, session_id, access)
    return export_service.build_report_export(db, session_id, access)


@router.get("/export/record/{session_id}", response_model=DataExportFile)
def export_record(
    session_id: int,
    export_format: ExportFormat = Query(default="md", alias="format"),
    db: Session = Depends(get_sessions_db),
    access: str | None = Depends(extract_token),
):
    """Download the plain interviewer/candidate transcript for one session."""
    if export_format == "json":
        return export_service.build_record_export_json(db, session_id, access)
    return export_service.build_record_export(db, session_id, access)
