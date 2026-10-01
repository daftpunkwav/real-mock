# resume/

Resume domain: upload, parsing, deep review, and server-side paginated preview.

| Layer | Contents |
| --- | --- |
| `routes/` | `upload.py` / `crud.py` / `file.py` (upload, CRUD, preview), `analyze.py` (deep review: JSON `POST /analyze` plus SSE `/analyze/stream` with live plan / tool / thinking events), `parse_retry.py` (re-dispatch of a failed background parse), and `router.py` (mounts the handlers with rate-limit dependencies) |
| [`services/`](services/README.md) | Ingest pipeline (`ingest.py`: disk placement, text extraction, LLM parsing, persistence), extraction / parsing (`extract.py`, `text_extract.py`, `parser.py`), analysis (`analysis.py`, `analysis_normalize.py`, `review_context.py`, `sites.py`, `repo_evidence.py`, `score_anchor.py`), rendering (`render.py`: deterministic PDF page → PNG for preview and vision fallback), slot cap (`analyze_slots.py`), storage (`store.py`, `files.py`, `resume_versions.py`), response mapping (`resume_mappers.py`), contract drift guard (`contract_guard.py`) |
| `agents/` | `review.py` (review agent: tool loop, event callbacks), `review_json.py` (JSON finalize with evidence-grounded self-correction), `review_prompts.py` (finalize-phase notices, budget / circuit-breaker refusal texts, text-only degradation notice), `process.py` (review-plan tool: model-owned 8–15 step list, rendered by the frontend as live progress), `payload.py` (first review message: vision page images or parsed text) and `observe.py` (tool-observation parsing for the live UI) |
| `schemas/` | `limits.py` (`MAX_PARALLEL_ANALYZE = 3`), `request.py` / `response.py` / `analysis.py` / `resume.py` / `locale.py` |

Notes:

- The deep-review concurrency cap is per-process; a full cap raises A1007 immediately (no queueing). Keep a single worker locally.
- Image-based PDFs fall back to vision transcription: `render.py` supplies page images, extraction consumes them.

Tests: `apps/api/tests/resume/`.
