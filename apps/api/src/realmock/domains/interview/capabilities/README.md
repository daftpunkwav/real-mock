# interview/capabilities/

Interview-specific capabilities. They are consumed only by this domain, which is why they live here instead of `platform/capabilities/` (those stay cross-domain). Parent map: [../README.md](../README.md).

## `rag/` — company knowledge-base RAG

| Module | Purpose |
| --- | --- |
| `base.py` | `RAGBackend` protocol: implement it and register in the factory; callers stay unchanged |
| `factory.py` | Selects the backend from `settings.rag_backend`: local Chroma / stepfun / `none` placeholder |
| `company_rag.py` | Facade; with `llm=None` degrades to an empty stub (tests). Explicit delegation, no `__getattr__` magic |
| `local_backend.py` | Local Chroma + any OpenAI-compatible `/embeddings` endpoint |
| `stepfun_backend.py` | StepFun-managed `vector_stores`: retrieval as a built-in tool type in the OpenAI protocol (no `/embeddings` endpoint) |
| `stepfun_index_http.py` | HTTP layer for the StepFun index (create / upload / attach / verify); outbound traffic pinned like every egress |
| `_kb_data.py` | Pure data layer (collection name, shared constants) with no business dependencies |

## `sandbox/`

| Module | Purpose |
| --- | --- |
| `evaluator.py` | Live-coding test evaluator and execution bridge: validates candidate output against test cases, aggregates scores, formats results for the WebSocket protocol |

## `vision/`

| Module | Purpose |
| --- | --- |
| `agent.py` | `VisionAgent`: compresses one face-analysis frame (face detected / looking away / nervousness / face count) into a short state line for the realtime orchestrator snapshot (`vision_summary`) |

Tests: `apps/api/tests/interview/`.
