# RealMock Data Model

Two SQLite databases, one per `DeclarativeBase` (`platform/database.py`):

| File | Base | Schema management | Owners |
| --- | --- | --- | --- |
| `api.db` | `ApiBase` | Alembic chain in `apps/api/alembic/` (`cd apps/api && alembic upgrade head`) | profile / resume / settings domain tables |
| `sessions.db` | `SessionsBase` | `SessionsBase.metadata.create_all` at startup + per-domain `column_migrations.py` | prep / interview / records / growth + platform rate-limit bucket |

## api.db (Alembic-managed)

The chain in `apps/api/alembic/versions/` manages only tables attached to `ApiBase`, all defined in `realmock.platform.models`. `alembic/env.py` takes the URL from `Settings.api_database_url` and sets `target_metadata = ApiBase.metadata`.

| Revision | Change |
| --- | --- |
| `20260803_0001` | Baseline column backfill |
| `20260901_0002` | Model-profile uniqueness |
| `20260907_0003` | Resume lineage |
| `20260916_0004` | Provider full-url |
| `20260917_0005` | Provider meta (head) |

## sessions.db (create_all + column migrations)

Business ORM models must be registered before `create_all` but cannot live in `platform.database` (no platform-to-domain imports). `bootstrap/sessions_orm.py` owns this assembly: `register_sessions_domain_models(domains)` imports `domains/<name>/models` for the requested subset (`prep` / `interview` / `records` / `growth`; `None` = all, empty = platform tables only), and `sessions_column_migrations(domains)` merges each domain's `SESSIONS_MIGRATIONS` map from `column_migrations.py`. `bootstrap/db_bootstrap.py: bootstrap_databases_and_seed()` runs the sequence at startup: legacy-DB split check, model registration, `init_db()`, migrations, seed.

## Tables

### api.db — defined in `realmock.platform.models`

| Table | Domain | Purpose (key columns) |
| --- | --- | --- |
| `user_profiles` | profile | Single-tenant local profile, one row: name, school, major, tech_domains, target_role, expected_city, ... |
| `resumes` | resume | Uploaded resume and analysis: filename, file_type, raw_text, parsed_profile, is_active, score, analysis, family_id, version_n |
| `stage_configs` | settings | One row per processing stage (`stage` unique): provider, api_base, api_key, protocol, model, capability flags |
| `llm_providers` | settings | BYOK provider identity: `name` unique, enabled |
| `llm_provider_channels` | settings | Per-kind (`chat` / `stt` / `tts`) connection: `provider_id` + `kind` unique, api_base, full_url, protocol, api_key (`enc:` AES-GCM) |
| `model_profiles` | settings | Capability-declared model entries: `provider_id` + `model` unique, cap_chat / cap_vision / cap_audio_in / cap_audio_out / cap_reasoning |
| `task_bindings` | settings | Per-task default model entry: `task` unique, profile_id, fallback_handler, fallback_mode |
| `integration_credentials` | settings | Third-party secrets (GitHub PAT): `key` unique, secret_enc (AES-GCM) |
| `llm_settings` | settings (legacy) | Single-row wide table; source of the one-time legacy→`stage_configs` import — its existence gates that import (`platform/services/pipeline/legacy.py`), values are not otherwise read |

### sessions.db — attached to `SessionsBase`

| Table | Domain | Purpose (key columns) |
| --- | --- | --- |
| `rate_limit_buckets` | platform | Rate-limit buckets (shared table backend) |
| `prep_sessions` | prep | Prep coach sessions: target_role, target_company, messages, token_usage, prompt/completion/cached tokens, status, access_token, linked_session_id, summary, message_count |
| `prep_memories` | prep | Long-term prep memories: user-rated turns, facts, agent notes |
| `interview_sessions` | interview | In-progress room state: role / level / company, workflow_type, status, current_phase, agent_state, messages, ledger, report, overall_score, process_id, round_no, result, plan |
| `interview_processes` | interview | Multi-round pipeline; sessions hang off via process_id: max_rounds, current_round, round_plan, round_plan_status, process memory |
| `ws_session_leases` | interview | One active WS lease per session: `session_id` unique, lease_token |
| `company_briefs` | interview | Cached company / role / level / interview-type brief: `company_key` unique |
| `interview_reports` | records | Debrief report per session: `session_id` unique, status, payload, model_meta |
| `growth_records` | growth | Per-session growth snapshot: `session_id` unique, weak_skills, common_mistakes, training_plan |
| `growth_insights` | growth | Latest LLM growth insight: one row per profile (payload JSON, locale, session_count) |

## Runtime data location

All runtime state lives under `apps/api/src/realmock/platform/data/` (gitignored, except `stt_fixtures/`):

| Path | Content |
| --- | --- |
| `api.db` (+ `-wal` / `-shm`) | Archive / configuration database |
| `sessions.db` (+ `-wal` / `-shm`) | Session / runtime database |
| `chroma/` | Local RAG (Chroma) persistence |
| `system_learning.json` (+ `.lock`) | Growth system-learning state |
| `.secret.key` | Auto-generated master key when `SECRET_KEY` is unset |
| `stt_fixtures/` | Tracked test data (the only tracked entry) |

User uploads go to `platform/uploads/` (`Settings.upload_dir`), also untracked.

## SQLite pragmas

File-backed SQLite engines get these pragmas on connect (`platform/database.py: _sqlite_pragmas`):

| Pragma | Value |
| --- | --- |
| `journal_mode` | `WAL` |
| `busy_timeout` | `5000` |
| `synchronous` | `NORMAL` |
| `foreign_keys` | `ON` |
