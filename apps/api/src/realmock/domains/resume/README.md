# resume/

Resume domain: upload, parsing, deep review, and server-side paginated preview.

| Layer | Contents |
| --- | --- |
| `routes/` | `upload.py` / `crud.py` / `file.py` (upload, CRUD, preview) and `analyze.py` (deep review: JSON `POST /analyze` plus SSE `/analyze/stream` with live plan / tool / thinking events) |
| [`services/`](services/README.md) | Ingest pipeline (`ingest.py`: disk placement, text extraction, LLM parsing, persistence), extraction / parsing (`text_extract.py`, `parser.py`), analysis (`analysis.py`, `analysis_normalize.py`, `review_context.py`, `sites.py`, `repo_evidence.py`, `score_anchor.py`), rendering (`render.py`: deterministic PDF page → PNG for preview and vision fallback), slot cap (`analyze_slots.py`), storage (`store.py`, `files.py`, `resume_versions.py`), response mapping (`resume_mappers.py`) |
| `agents/` | `review.py` (review agent: tool loop, JSON finalize, event callbacks), `process.py` (review-plan tool: model-owned 8–15 step list, rendered by the frontend as live progress), `payload.py` (first review message: vision page images or parsed text) and `observe.py` (tool-observation parsing for the live UI) |
| `schemas/` | `limits.py` (`MAX_PARALLEL_ANALYZE = 3`), `request.py` / `response.py` / `analysis.py` / `resume.py` / `locale.py` |

Notes:

- The deep-review concurrency cap is per-process; a full cap raises A1007 immediately (no queueing). Keep a single worker locally.
- Image-based PDFs fall back to vision transcription: `render.py` supplies page images, extraction consumes them.

Tests: `apps/api/tests/resume/`.
