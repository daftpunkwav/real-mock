# RealMock HTTP API

The FastAPI aggregate app (`realmock.asgi:app`) mounts the seven domain routers under `/api/v1` and registers a rolling `/api` legacy alias. The full machine-readable contract is the root [`openapi.json`](../../openapi.json).

## Mounting and access control

| Aspect | Behavior |
| --- | --- |
| Mounting | `platform/router_mount.py: include_with_legacy_api_alias()` mounts every domain `service_router` under `/api/v1` and again under `/api` |
| Domain prefixes | Owned by each domain's router (`domains/<name>/router.py`): `/profile`, `/resume`, `/settings`, `/prep`, `/interview`, `/options`, `/records`, `/reports`, `/growth` |
| Local access | `platform/core/local_only.py: LOCAL_API_DEPENDENCIES` is applied at mount time to every HTTP route: `require_local_peer` (loopback peers only, else `A0405`) + `reject_cross_site_fetch` (browser `Sec-Fetch-Site: cross-site` rejected, `A0403`) |
| Capability tokens | Interview / prep / report content routes additionally require the session capability token (`platform/core/session_auth/extract.py`): header `X-Interview-Token` > cookie > query `token=` (non-prod only) |
| WebSocket | FastAPI dependencies do not run on WS scopes; `ws/interview` performs origin + token checks in the route body — see [realtime-protocol.md](realtime-protocol.md) |
| Health | `GET /health` (registered on the app, outside the `/api` prefixes) |

## Contract pipeline

`scripts/export_openapi.py` → root `openapi.json` → `apps/web/src/types/generated/api.d.ts` (run `cd apps/web && npm run generate:api-types`). Guards: `apps/api/tests/architecture/test_api_v1_paths.py` (both prefixes exist) and `test_openapi_contract_sync.py` (committed `openapi.json` matches the live app schema).

## Endpoints by domain

Paths below are relative to `/api/v1`; each also exists under the legacy `/api` alias.

### profile — `domains/profile/routes/profile.py`

| Methods | Path | Group |
| --- | --- | --- |
| GET / PUT | `/profile` | single profile row: read / full-replace update |
| POST | `/profile/clear` | blank every update-contract field |

### resume — `domains/resume/routes/` (`router.py` aggregates `upload` / `crud` / `file` / `analyze`)

| Methods | Path | Group |
| --- | --- | --- |
| POST | `/resume/upload`, `/resume/{resume_id}/versions` | upload / add version |
| GET | `/resume/limits`, `/resume/list`, `/resume/{resume_id}` | limits, listing, single resume |
| POST | `/resume/{resume_id}/activate` | set active resume |
| DELETE | `/resume/{resume_id}`, `/resume/analyses`, `/resume/collection` | delete one / clear review results / delete all |
| GET | `/resume/{resume_id}/file`, `/resume/{resume_id}/pages`, `/resume/{resume_id}/pages/{page_no}` | file download and paginated page images |
| POST | `/resume/{resume_id}/analyze`, `/resume/{resume_id}/analyze/stream` | deep review (JSON / SSE) |

### settings — `domains/settings/routes/` (`models` / `stages` / `model_tests` / `integrations`)

| Methods | Path | Group |
| --- | --- | --- |
| GET | `/settings/models`, `/settings/providers`, `/settings/vendors`, `/settings/bindings` | catalogs and current config |
| POST / PUT / DELETE | `/settings/providers`, `/settings/providers/{provider_id}`, `/settings/providers/{provider_id}/models`, `/settings/models/{model_id}` | provider and model CRUD |
| PUT / GET | `/settings/providers/{provider_id}/channels/{kind}`, `.../catalog` | channel config and catalog |
| PUT | `/settings/bindings/{task}` | task-to-model bindings |
| GET / PUT | `/settings/stages`, `/settings/stages/{stage}` | stage configs (recognize / reason / speak) |
| GET | `/settings/catalog` | stage catalog |
| POST | `/settings/test/{stage}`, `/settings/test/model/{model_id}` | connectivity tests |
| GET / POST / DELETE | `/settings/integrations/github` | GitHub link |
| POST | `/settings/integrations/github/test` | GitHub link test |

### prep — `domains/prep/routes/` (`router.py` mounts `lists` / `create` / `chat` / `history` / `manage` / `memories`)

| Methods | Path | Group |
| --- | --- | --- |
| GET | `/prep/resumes`, `/prep/sessions` | listing |
| POST | `/prep/sessions` | create session (sets capability cookie) |
| POST | `/prep/sessions/{session_id}/message`, `/prep/sessions/{session_id}/message/stream` | chat turn (JSON / SSE) |
| GET | `/prep/sessions/{session_id}/messages`, `/prep/sessions/{session_id}/context` | history and context |
| POST | `/prep/sessions/{session_id}/compact`, `/prep/sessions/{session_id}/fork`, `/prep/sessions/{session_id}/messages/truncate` | history operations |
| PATCH | `/prep/sessions/{session_id}/summary` | update rolling summary |
| DELETE | `/prep/sessions/{session_id}` | delete session |
| POST | `/prep/sessions/purge-empty`, `/prep/sessions/purge-all` | purge |
| PATCH / PUT / POST | `/prep/sessions/{session_id}/archive`, `/prep/sessions/{session_id}/link`, `/prep/sessions/{session_id}/reissue` | archive / link resume / reissue token |
| GET / POST | `/prep/memories`, `/prep/memories/tags`, `/prep/memories/batch-delete` | long-term memories |
| GET / PATCH / DELETE | `/prep/memories/{memory_id}` | memory item |

Content-reading routes (message / stream / messages / fork / context) require the capability token; owner-level routes require same-origin CSRF instead.

### interview — `domains/interview/routes/` (`interview.py` mounts `sessions` / `turns` / `processes`; plus `brief.py`, `options.py`, `ws/`)

| Methods | Path | Group |
| --- | --- | --- |
| GET | `/interview/resumes` | resume picker |
| POST / GET | `/interview/sessions` | create / list standalone sessions |
| GET | `/interview/sessions/{session_id}`, `/interview/sessions/{session_id}/messages` | session detail and messages |
| POST | `/interview/sessions/{session_id}/start`, `/interview/sessions/{session_id}/message`, `/interview/sessions/{session_id}/finish` | HTTP turn API (the interview room itself runs over WebSocket) |
| POST / GET | `/interview/processes` | create (with round-1 session) / list multi-round processes |
| GET | `/interview/processes/{process_id}` | process detail (round lineage, round plan) |
| POST | `/interview/processes/{process_id}/rounds` | create next round — see [interview-flow.md](../interview-flow.md) |
| POST / DELETE | `/interview/company-brief`, `/interview/company-briefs` | company research brief |
| GET | `/options` | setup-page options (workflows / personalities / voices / avatars) |
| WS | `/ws/interview/{session_id}` | realtime room — see [realtime-protocol.md](realtime-protocol.md) |

### records — `domains/records/routes/` (`history` / `report`)

| Methods | Path | Group |
| --- | --- | --- |
| GET | `/records/sessions` | session history |
| GET | `/records/sessions/{session_id}/ledger` | frozen session ledger |
| GET | `/reports/{session_id}` | debrief report (`A2004` while pending / generating, `A2005` when failed) |
| POST | `/reports/{session_id}/retry` | re-run report generation (idempotent) |
| GET | `/reports/{session_id}/stream` | pseudo-streamed report (generates once if pending) |

### growth — `domains/growth/routes/router.py`

| Methods | Path | Group |
| --- | --- | --- |
| GET | `/growth/history` | interview history statistics |
| GET | `/growth/system-insights` | system insight report |
| GET | `/growth/aggregated` | aggregated growth view |
