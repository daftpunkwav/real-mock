"""Data-management schemas: wipe-all response summary."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DataClearResponse(BaseModel):
    """Per-area row counts removed by the wipe-all endpoint."""

    #: sessions-db rows deleted, keyed by table name.
    sessions_tables: dict[str, int] = Field(default_factory=dict)
    #: api-db content rows deleted, keyed by table name.
    api_tables: dict[str, int] = Field(default_factory=dict)
    #: resume files removed from the upload directory.
    upload_files: int = 0
    #: True when the growth learning JSON sidecar was removed.
    learning_reset: bool = False


__all__ = ["DataClearResponse"]
