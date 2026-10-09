"""Data-export file contract shared by the exporting domains.

Records and resume each expose export endpoints that hand back one
self-contained file (markdown or JSON) as a string; the frontend turns it
into a download. One schema keeps the clients' shapes identical.
"""

from __future__ import annotations

from pydantic import BaseModel

#: MIME type of an exported markdown document.
MIME_MARKDOWN = "text/markdown; charset=utf-8"
#: MIME type of an exported JSON document.
MIME_JSON = "application/json; charset=utf-8"


class DataExportFile(BaseModel):
    """A single exported file, ready to be saved by the client."""

    #: Suggested download filename (with extension).
    filename: str
    #: MIME type matching the content (markdown or JSON).
    mime: str
    #: Full file content.
    content: str


__all__ = ["DataExportFile", "MIME_JSON", "MIME_MARKDOWN"]
