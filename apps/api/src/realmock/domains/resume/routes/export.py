"""Resume export HTTP handler: deep-review analysis as a downloadable file."""

from __future__ import annotations

from typing import Literal

from fastapi import Depends
from sqlalchemy.orm import Session

from realmock.domains.resume.services import export as export_service
from realmock.platform.contracts.data_export import DataExportFile
from realmock.platform.database import get_db

ExportFormat = Literal["md", "json"]


def export_analysis(
    resume_id: int,
    format: ExportFormat = "md",
    include_resume: bool = False,
    db: Session = Depends(get_db),
) -> DataExportFile:
    """Download one resume's deep-review analysis; optionally fold in the resume."""
    return export_service.build_analysis_export(
        db,
        resume_id,
        fmt=format,
        include_resume=include_resume,
    )
