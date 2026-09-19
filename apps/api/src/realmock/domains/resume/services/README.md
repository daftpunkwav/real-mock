# resume/services/

Business logic for the resume domain: ingest, deep review, market analysis, rendering, storage.

## Ingest and parsing

| Module | Purpose |
| --- | --- |
| `ingest.py` | Upload pipeline: disk placement, extraction, parsing, persistence (no FastAPI imports) |
| `text_extract.py` | Plain-text extraction under catalog resource limits |
| `extract.py` | Extraction orchestration (incl. vision fallback for image-based PDFs) |
| `parser.py` | AI transcription and structured parsing |
| `render.py` | Deterministic PDF page → PNG (preview and vision-fallback images) |

## Deep review

| Module | Purpose |
| --- | --- |
| `analysis.py` | Review orchestration: heal text → agent loop → persist |
| `review_context.py` | DB-backed input builders for the review agent |
| `analysis_prompt.py` | Review system prompt and shared JSON schema text |
| `analysis_market.py` | Market search: plan queries, fetch web context, cache |
| `market_queries.py` / `market_keywords.py` | Market query / keyword generation |
| `sites.py` | Site allowlist for market web search |
| `repo_evidence.py` | GitHub repository evidence gathering |
| `analysis_normalize.py` | Review payload normalization |
| `score_anchor.py` | Prior-version score reference for re-review calibration |
| `analyze_slots.py` | In-process concurrency cap (A1007 when full) |

## Storage and contracts

| Module | Purpose |
| --- | --- |
| `store.py` | Persistence: rows, families, on-disk files |
| `files.py` | On-disk lookup for stored uploads |
| `resume_versions.py` | Version lineage: family identity, scored history |
| `resume_mappers.py` | Tolerant JSON coercion and API response assembly |
| `contract_guard.py` | Contract ↔ ORM / catalog drift guard (fails at import time) |

The composing agents live in `../agents`.
