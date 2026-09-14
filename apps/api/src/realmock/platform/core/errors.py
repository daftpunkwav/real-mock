"""Site-wide error-code registry (this CATALOG is authoritative; register new codes here first).

Usage:
    from realmock.platform.core.errors import raise_error

    raise_error("A1005")                       # catalog default message
    raise_error("A0413", max=10)               # format {max} in message
    raise_error("C0001", cause=e)              # chain the original exception

Design notes:
- ``ApiBusinessError`` subclasses ``HTTPException``, so existing
  ``except HTTPException`` handlers and the ``core/error_handlers.py`` envelope handler
  keep working;
- the handler reads ``exc.error_code``; unmigrated ``raise HTTPException``
  paths fall back to ``http_{status}`` codes and do not collide.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

from fastapi import HTTPException


@dataclass(frozen=True)
class ErrorSpec:
    """One error-code specification."""

    code: str
    http_status: int
    message: str          # English default copy (may include {name}-style placeholders)
    hint: str = ""        # English recovery hint
    retryable: bool = False


# ---------------------------------------------------------------------------
# Catalog (authoritative; register new codes here first)
# ---------------------------------------------------------------------------

CATALOG: dict[str, ErrorSpec] = {
    # A0 generic
    "A0001": ErrorSpec("A0001", 422, "Request validation failed", "Check that the input is complete and correctly formatted"),
    "A0002": ErrorSpec("A0002", 429, "Too many requests, please try again later", "Slow down; if this keeps happening, wait 1 minute", True),
    "A0003": ErrorSpec("A0003", 400, "Text too long (limit: {max} characters)", "Split the text into parts or shorten it"),
    "A0004": ErrorSpec("A0004", 400, "Audio too large; speak in shorter turns or type instead", "Keep each turn under 2 minutes"),
    "A0005": ErrorSpec("A0005", 400, "File is empty", "Choose a non-empty file and upload again"),
    "A0006": ErrorSpec("A0006", 400, "API Key not configured", "Go to Settings and fill in the reasoning processor's API Base and Key"),
    "A0007": ErrorSpec("A0007", 400, "Unsafe URL", "Only public https URLs are allowed; enable ALLOW_LOCAL_LLM explicitly in .env for local models"),
    "A0401": ErrorSpec("A0401", 403, "No access to this session", "The session token has expired; return to the list page and re-enter"),
    "A0403": ErrorSpec("A0403", 403, "Cross-site request rejected", "Start the action from this app's pages, not by calling the API directly"),
    "A0404": ErrorSpec("A0404", 404, "The requested resource does not exist", "It may have been deleted; go back to the list page and refresh"),
    "A0405": ErrorSpec("A0405", 403, "Management endpoints allow local access only", "Access from the browser on the machine running this instance"),
    "A0413": ErrorSpec("A0413", 413, "File exceeds the {max}MB limit", "Compress the file or switch to DOCX/TXT and retry"),
    # A1 resume
    "A1001": ErrorSpec("A1001", 400, "File name cannot be empty", "Check the selected file and retry"),
    "A1002": ErrorSpec("A1002", 400, "Unsupported file format. Allowed: {exts}", "Upload a resume in PDF / DOCX / MD / TXT format"),
    "A1003": ErrorSpec("A1003", 400, "File content does not match its extension", "The file may be corrupted or tampered with; re-export it and upload again"),
    "A1004": ErrorSpec("A1004", 400, "Failed to parse the file", "Scanned PDFs contain no extractable text; use a text-based PDF or DOCX"),
    "A1005": ErrorSpec("A1005", 404, "Resume not found", "The resume may have been deleted; refresh the list"),
    "A1006": ErrorSpec("A1006", 400, "Image-based PDF has no extractable text", "For scanned/image-exported resumes, bind a vision-capable model to the chat task in Settings and re-upload; or use a text-based PDF / DOCX"),
    "A1007": ErrorSpec("A1007", 429, "3 resumes are already under review", "Deep review runs at most 3 resumes in parallel; wait for one to finish", True),
    "A1008": ErrorSpec("A1008", 409, "This resume already has {max} versions", "Delete an older version or upload it as a new resume"),
    # A2 interview
    "A2001": ErrorSpec("A2001", 404, "Interview session not found", "The session may have expired or been deleted; create a new interview"),
    "A2002": ErrorSpec("A2002", 400, "Interview already finished", "This interview is complete; see the report page for results"),
    "A2003": ErrorSpec("A2003", 400, "Interview not finished yet", "Finish the interview before viewing the report"),
    "A2004": ErrorSpec("A2004", 404, "Report not generated yet", "The report is being generated in the background; refresh later or retry", True),
    "A2005": ErrorSpec("A2005", 409, "Report generation failed", "Click regenerate; if it keeps failing, check the reasoning processor settings", True),
    "A2006": ErrorSpec("A2006", 409, "No next round available", "Only a passed latest round with rounds remaining can continue; start a new process instead"),
    # A3 coaching
    "A3001": ErrorSpec("A3001", 404, "Coaching session not found", "The session may have expired; create a new one"),
    "A3002": ErrorSpec("A3002", 400, "Coaching session already closed", "This coaching session is closed; create a new one"),
    "A3003": ErrorSpec("A3003", 409, "Coaching session changed during the operation", "The history changed mid-operation; refresh and retry"),
    "A3004": ErrorSpec("A3004", 404, "No compaction summary yet", "Compact the session first, then edit the summary"),
    # A4 settings
    "A4001": ErrorSpec("A4001", 400, "The selected provider does not support interview reasoning", "Switch to a provider that supports Chat Completions in Settings"),
    "A4002": ErrorSpec("A4002", 400, "This recognition processor does not support transcription", "Change the recognition processor or use local Whisper"),
    "A4003": ErrorSpec("A4003", 400, "Invalid speech configuration", "Check the recognition/speech processor's Base, Key and model name"),
    "A4004": ErrorSpec("A4004", 400, "stage must be recognize / reason / speak", "Start tests from the Settings page buttons, not by calling the API directly"),
    "A4005": ErrorSpec("A4005", 404, "Provider or model entry not found", "It may have been deleted; refresh the settings page and retry"),
    # B system
    "B0001": ErrorSpec("B0001", 500, "Internal server error, please try again later", "If it persists, report it to the developer with the trace_id", True),
    "B1001": ErrorSpec("B1001", 500, "Failed to persist the result, please try again later", "Local write error (file/database); if it persists, check disk space and file permissions", True),
    # C third-party
    "C0001": ErrorSpec("C0001", 502, "AI service temporarily unavailable, please try again later", "Check the API Key quota and network; if it persists, test connectivity in Settings", True),
    "C0002": ErrorSpec("C0002", 502, "The model returned no valid result, please try again later", "The model may be incompatible (reasoning-only/empty output); try another model", True),
    "C1001": ErrorSpec("C1001", 502, "Report generation failed, please try again later", "Click regenerate on the report page; spoken wrap-up content is unaffected", True),
    "C2001": ErrorSpec("C2001", 200, "Could not recognize the speech; speak again or type instead", "Move closer to the microphone, reduce background noise, or type your answer", True),
    "C2002": ErrorSpec("C2002", 200, "Speech synthesis failed; subtitles only for this turn", "Check the speech processor settings; you can switch to Edge TTS in Settings", True),
    "C3001": ErrorSpec("C3001", 200, "Web search temporarily unavailable; continuing with general knowledge", "The search failure does not block the main flow; retry later for live info", True),
    "C4001": ErrorSpec("C4001", 200, "Knowledge base retrieval failed; continuing without it", "The fallback does not affect the interview; check RAG config and embeddings service", True),
}


class ApiBusinessError(HTTPException):
    """HTTP exception that carries a business error code.

    Subclasses :class:`HTTPException` so existing ``raise HTTPException``
    call sites keep the same status_code/detail semantics, while adding
    ``error_code`` / ``error_hint`` / ``error_retryable`` for the envelope
    handler to build business-level responses.

    Extra response headers (e.g. 429 Retry-After) can be passed as
    ``headers=...`` at construction, or chained via ``with_headers(...)``
    before raise. The envelope handler forwards them to JSONResponse.
    """

    def __init__(
        self,
        spec: ErrorSpec,
        *,
        message: str,
        cause: Exception | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=spec.http_status,
            detail=message,
            headers=headers,
        )
        self.error_code = spec.code
        self.error_hint = spec.hint
        self.error_retryable = spec.retryable
        if cause is not None:
            self.__cause__ = cause

    def with_headers(self, headers: dict[str, str]) -> "ApiBusinessError":
        """Chain-append response headers; returns self for pre-raise assembly.

        Usage::

            raise ApiBusinessError(spec, message=...)\n
                .with_headers({"Retry-After": "60"})
        """
        existing = dict(self.headers or {})
        existing.update(headers)
        self.headers = existing
        return self


def get_spec(code: str) -> ErrorSpec:
    """Look up :class:`ErrorSpec` by code; unknown codes fall back to B0001.

    Guarantees :func:`raise_error` never raises KeyError for arbitrary
    strings, so temporary references to unregistered codes still work
    during migrations.
    """
    return CATALOG.get(code) or CATALOG["B0001"]


def raise_error(code: str, *, cause: Exception | None = None, **fmt: object) -> NoReturn:
    """Raise a business exception using the catalog default message.

    Args:
    - code: error code; unregistered codes fall back to B0001 (never KeyError)
    - cause: original exception chained onto __cause__
    - **fmt: format placeholders in the catalog message, e.g.
      raise_error("A0413", max=10) -> "File exceeds the 10MB limit"

    For fully custom messages (e.g. dynamic URL validation copy in settings)::
    raise ApiBusinessError(get_spec("A0007"), message="<dynamic copy>")
    """
    spec = get_spec(code)
    message = spec.message.format(**fmt) if fmt else spec.message
    raise ApiBusinessError(spec, message=message, cause=cause)


__all__ = ["CATALOG", "ApiBusinessError", "ErrorSpec", "get_spec", "raise_error"]
