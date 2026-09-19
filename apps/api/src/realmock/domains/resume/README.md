# resume/

Resume domain: upload, parsing, deep review, and server-side paginated preview.

| Layer | Contents |
| --- | --- |
| `routes/` | `upload.py` / `crud.py` / `file.py` (upload, CRUD, preview) and `analyze.py` (deep review: JSON `POST /analyze` plus SSE `/analyze/stream` with live plan / tool / thinking events) |
| [`services/`](services/README.md) | Ingest pipeline (`ingest.py`: disk placement, text extraction, LLM parsing, persistence), analysis (`analysis*.py`, `market_*.py`, `sites.py`, `repo_evidence.py`, `score_anchor.py`), rendering (`render.py`: deterministic PDF page → PNG for preview and vision fallback), slot cap (`analyze_slots.py`), storage (`store.py`, `files.py`, `resume_versions.py`) |
| `agents/` | `review.py` (review agent: tool loop, JSON finalize, event callbacks) and `process.py` (review-plan tool: model-owned 8–15 step list, rendered by the frontend as live progress) |
| `schemas/` | `limits.py` (`MAX_PARALLEL_ANALYZE = 3`), `request.py` / `response.py` / `analysis.py` / `resume.py` / `locale.py` |

Notes:

- The deep-review concurrency cap is per-process; a full cap raises A1007 immediately (no queueing). Keep a single worker locally.
- Image-based PDFs fall back to vision transcription: `render.py` supplies page images, extraction consumes them.

Tests: `apps/api/tests/resume/`.
