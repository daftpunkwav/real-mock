# RealMock Configuration

Backend configuration lives in `apps/api/src/realmock/platform/config.py` (`Settings`, pydantic-settings). Environment variables use unprefixed field names; values may also come from `apps/api/src/realmock/platform/.env` (`PLATFORM_ROOT/.env`). `get_settings()` caches a single instance.

## Backend settings

| Env var | Field | Purpose | Default |
| --- | --- | --- | --- |
| `ENV` | `env` | `dev` / `prod`; controls CORS strictness and the local-LLM gate | `dev` |
| `HOST` | `host` | Bind address; `0.0.0.0` for LAN debugging | `127.0.0.1` |
| `PORT` | `port` | Bind port | `8081` |
| `CORS_ORIGINS` | `cors_origins` | Comma-separated allowed origins | `http://localhost:8080,http://127.0.0.1:8080` |
| `LLM_API_BASE` | `llm_api_base` | BYOK chat Base URL | `""` (empty) |
| `LLM_API_KEY` | `llm_api_key` | BYOK chat API key | `""` (empty) |
| `LLM_MODEL` | `llm_model` | BYOK chat model | `""` (empty) |
| `LLM_MAX_TOKENS` | `llm_max_tokens` | Max output tokens | `64000` (`DEFAULT_MAX_OUTPUT_TOKENS`) |
| `LLM_CONTEXT_WINDOW` | `llm_context_window` | Context window | `256000` (`DEFAULT_CONTEXT_WINDOW`) |
| `LLM_EMBEDDINGS_BASE` | `llm_embeddings_base` | Embeddings Base URL override; `None` falls back to `llm_api_base` | `None` |
| `LLM_EMBEDDINGS_KEY` | `llm_embeddings_key` | Embeddings key override; `None` falls back to `llm_api_key` | `None` |
| `LLM_EMBEDDINGS_MODEL` | `llm_embeddings_model` | Embeddings model override; `None` falls back to `llm_model` | `None` |
| `RAG_BACKEND` | `rag_backend` | `local` / `stepfun` / `none` (`RAGBackendKind`) | `local` |
| `STEPFUN_VECTOR_STORE_ID` | `stepfun_vector_store_id` | Reuse an existing StepFun vector store; empty creates one at startup | `None` |
| `API_DATABASE_URL` | `api_database_url` | api.db URL | `sqlite:///{platform}/data/api.db` |
| `SESSIONS_DATABASE_URL` | `sessions_database_url` | sessions.db URL | `sqlite:///{platform}/data/sessions.db` |
| `DATABASE_URL` | `database_url` | Legacy alias; when set to a non-default path it overrides the sessions DB URL | `sqlite:///{platform}/data/sessions.db` |
| `UPLOAD_DIR` | `upload_dir` | Upload directory | `{platform}/uploads` |
| `WHISPER_MODEL` | `whisper_model` | STT model; `tiny`/`base`/`small`/... selects local faster-whisper | `whisper-1` |
| `TTS_VOICE` | `tts_voice` | TTS voice | `zh-CN-XiaoxiaoNeural` |
| `SILENCE_NUDGE_SECONDS` | `silence_nudge_seconds` | Interview silence nudge interval | `10` (range 1-600) |
| `GITHUB_TOKEN` | `github_token` | Optional GitHub PAT (raises API quota) | `""` (empty) |
| `INTERVIEW_TOOLS_ENABLED` | `interview_tools_enabled` | Interview agent function-calling tool loop | `True` |
| `INTERVIEW_MAX_TOOL_ROUNDS` | `interview_max_tool_rounds` | Tool-loop round cap | `3` (range 0-6) |
| `ALLOW_LOCAL_LLM` | `allow_local_llm` | Allow local / private-network `base_url` | `False` |
| `WS_LEASE_BACKEND` | `ws_lease_backend` | WS lease store: `memory` (single worker) / `database` (multi-worker) | `memory` |
| `RATELIMIT_BACKEND` | `ratelimit_backend` | Rate-limit store: `memory` / `database` | `memory` |
| `TRUSTED_PROXY_CIDRS` | `trusted_proxy_cidrs` | Comma-separated trusted reverse-proxy CIDRs; empty uses `request.client.host` only | `""` (empty) |
| `COOKIE_SECURE` | `cookie_secure` | `None` = auto (https or trusted proxy `X-Forwarded-Proto: https`) | `None` |

## Environment variables read outside `Settings`

| Env var | Read by | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | `platform/core/secrets.py` | Master key for field encryption (base64 or plaintext, >= 16 bytes) |
| `TEST_MODE` | `asgi.py`, `bootstrap/db_bootstrap.py`, `platform/app_factory.py` | `1` switches to test bootstrap (temp DB via conftest, no seed, no legacy split) |
| `DATABASE_URL` | `config.py` (model validator) | Legacy override, synced to `sessions_database_url` |

## Validation at startup

| Rule | Enforced in |
| --- | --- |
| `env=prod` rejects `CORS_ORIGINS` containing `*` (dev logs a warning) | `asgi.py: _check_cors_policy` |
| `env=prod` rejects `allow_local_llm=True` | `config.py` model validator |
| `env=prod` requires `SECRET_KEY` (>= 16 bytes); without it, startup raises | `asgi.py: _check_secret_key_policy` |
| `ws_lease_backend` / `ratelimit_backend` = `memory` logs a multi-worker warning | `bootstrap/db_bootstrap.py: _warn_inmemory_backends` |
| `rag_backend=stepfun` without `stepfun_vector_store_id` logs a warning; startup attempts to create a vector store | `config.py` model validator |

## Frontend variables

`apps/web/.env.example` (copy to `.env.local`):

| Variable | Purpose | Example default |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE` | Backend REST API base URL (direct connection, no Next.js proxy) | `http://localhost:8081` |
| `NEXT_PUBLIC_WS_URL` | Direct WebSocket URL | `ws://localhost:8081` |
| `NEXT_PUBLIC_STREAM_API_BASE` | Direct SSE URL; must share an origin with `NEXT_PUBLIC_API_BASE` | `http://localhost:8081` |

Port planning documented in `.env.example` and `config.py`: consolidated form runs frontend 8080 / backend 8081; standalone form runs api 8081 / agent 8082 / interview 8083.

## BYOK provider / model configuration

Provider and model configuration is stored in the database (settings domain), not in config files: `llm_providers`, `llm_provider_channels`, `model_profiles`, `task_bindings` and `stage_configs`; the GitHub PAT is stored in `integration_credentials`. `Settings` ships no default model — `llm_api_base` / `llm_api_key` / `llm_model` default to empty strings.

API keys are encrypted at rest with AES-256-GCM (`platform/core/secrets.py`):

| Aspect | Value |
| --- | --- |
| Ciphertext format | `enc:v2:<b64-salt16>:<b64-nonce12>:<b64-tag16>:<b64-cipher>` |
| Key derivation | PBKDF2-HMAC-SHA256, 200000 iterations, per-ciphertext random salt; random 12-byte GCM nonce |
| Master key source | `SECRET_KEY` env; otherwise a random 32-byte key persisted to `platform/data/.secret.key` |
| Legacy ciphertext | `enc:v1` raises `LegacySecretFormatError`; the key must be re-saved on the Settings page |
| Readback | Secrets are never returned in clear; list payloads expose a tail mask only |

Runtime resolution order for LLM calls (`platform/capabilities/ai/llm/client/from_db.py`): the model-profile task bindings in the database, then the `stage_configs` fallback; environment variables are the last-resort fallback. On startup, `platform/services/seed.py: seed_llm_settings()` writes the `reason` stage from `LLM_*` env values into `stage_configs` (key encrypted) only when the database has no stage configuration and the environment provides a key.
