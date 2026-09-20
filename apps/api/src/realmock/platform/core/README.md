# platform/core/

Kernel utilities shared by every domain: configuration-adjacent constants, the error registry, logging, SSE, rate limiting, secrets, security helpers, and session auth. Parent map: [../README.md](../README.md).

## Top-level modules

| Module | Purpose |
| --- | --- |
| `constants.py` | Global protocol constants — string literals shared 1:1 with the frontend `src/config/*.ts` |
| `errors.py` | Site-wide error-code registry; the catalog is authoritative — new codes register here first (`raise_error`) |
| `error_handlers.py` | Unified exception handlers and error-envelope construction; the app factory only registers them |
| `logging.py` | Structured JSON-style logging with trace ids; `RedactFilter` replaces API keys / Authorization headers in log output |
| `sse.py` | Shared SSE helpers: error envelopes (business errors keep catalog code / message / retryable), queue pump, streaming responses |
| `ratelimit.py` | Lightweight in-process rate limiting (no external services) for expensive endpoints (LLM calls, uploads, analysis) |
| `file_lock.py` | Cross-process file lock: `msvcrt.locking` on Windows, `fcntl.flock` on POSIX |
| `migrate.py` | SQLite column-completion migration engine + `api.db` manifest + Alembic version stamp; business DDL is owned by each domain's `column_migrations.py` |
| `local_only.py` | Local-exposure guards: `require_local_peer` (loopback-only management endpoints) and the mount-level cross-site guard (`Sec-Fetch-Site` / Origin-Referer, error `A0403`) |
| `secrets.py` | AES-256-GCM authenticated encryption for stored provider keys (`enc:v2:...`); key from `SECRET_KEY` env or `data/.secret.key` |
| `prompts.py` | Shared agent/LLM prompt fragments; output rules go through `with_agent_output_rules` |
| `agent_error_log.py` | Opt-in JSONL log for agent tool/loop failures (`REALMOCK_AGENT_ERROR_LOG=1`); disabled by default |

## `security/` — input and URL safety

| Module | Purpose |
| --- | --- |
| `file.py` | Filename sanitization (basename, character allowlist, length cap), path-traversal defense, magic-number sniffing |
| `url.py` | URL/SSRF filtering: private / CGNAT / multicast ranges, port allowlist, multi-record + IPv6 resolution; policy functions stay here (tests patch `url._resolve_all`) |
| `url_pin.py` | DNS pinning: resolve once, connect to the fixed IP (DNS-rebinding TOCTOU); `PinnedHostTransport` for httpx |
| `redact.py` | API-key-shaped string redaction |

## `session_auth/` — session capability tokens

No multi-user login; mutating operations require the `access_token` issued at session creation, delivered as an HttpOnly cookie (`iv_{id}` / `prep_{id}`); the `X-Interview-Token` header remains supported for tests and migration, and production rejects query-string tokens.

| Module | Purpose |
| --- | --- |
| `cookies.py` | Cookie naming / writing / clearing, Secure detection, 90-day capability-cookie lifetime |
| `tokens.py` | Token generation (url-safe, ~32 bytes entropy) and constant-time comparison |
| `csrf.py` | Cookie-only CSRF mitigation: Origin/Referer must be in the CORS allowlist |
| `extract.py` | Token extraction from cookie / header / (dev-only) query, per scope |

Tests: `apps/api/tests/platform_core/` and session-level integration in `apps/api/tests/sessions/`.
