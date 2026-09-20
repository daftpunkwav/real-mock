# RealMock 数据模型

两个 SQLite 数据库，各对应一个 `DeclarativeBase`（`platform/database.py`）：

| 文件 | Base | Schema 管理 | 归属 |
| --- | --- | --- | --- |
| `api.db` | `ApiBase` | `apps/api/alembic/` 迁移链（`cd apps/api && alembic upgrade head`） | profile / resume / settings 域表 |
| `sessions.db` | `SessionsBase` | 启动时 `SessionsBase.metadata.create_all` 建表 + 各域 `column_migrations.py` 列迁移 | prep / interview / records / growth + platform 限流桶 |

## api.db（Alembic 管理）

`apps/api/alembic/versions/` 中的迁移链只管理挂载在 `ApiBase` 上的表，全部定义于 `realmock.platform.models`。`alembic/env.py` 从 `Settings.api_database_url` 取连接 URL，并设置 `target_metadata = ApiBase.metadata`。

| 版本 | 变更 |
| --- | --- |
| `20260803_0001` | 基线列回填 |
| `20260901_0002` | model-profile 唯一性 |
| `20260907_0003` | 简历版本谱系 |
| `20260916_0004` | 供应商完整 URL |
| `20260917_0005` | 供应商 meta（head） |

## sessions.db（create_all + 列迁移）

业务 ORM 必须在 `create_all` 之前注册，但不能放在 `platform.database` 中（禁止 platform 到 domain 的导入）。该组装由 `bootstrap/sessions_orm.py` 负责：`register_sessions_domain_models(domains)` 按需导入 `domains/<name>/models`（子集为 `prep` / `interview` / `records` / `growth`；`None` = 全部，空集 = 仅 platform 表）；`sessions_column_migrations(domains)` 从各域 `column_migrations.py` 合并 `SESSIONS_MIGRATIONS` 映射。`bootstrap/db_bootstrap.py: bootstrap_databases_and_seed()` 在启动时按序执行：legacy 单库拆分检查、模型注册、`init_db()`、迁移、种子数据。

## 表清单

### api.db — 定义于 `realmock.platform.models`

| 表 | 域 | 用途（关键列） |
| --- | --- | --- |
| `user_profiles` | profile | 单租户本地画像，单行：name、school、major、tech_domains、target_role、expected_city 等 |
| `resumes` | resume | 上传简历与解析结果：filename、file_type、raw_text、parsed_profile、is_active、score、analysis、family_id、version_n |
| `stage_configs` | settings | 每个处理阶段一行（`stage` 唯一）：provider、api_base、api_key、protocol、model、能力标志 |
| `llm_providers` | settings | BYOK 供应商身份：`name` 唯一、enabled |
| `llm_provider_channels` | settings | 按用途（`chat` / `stt` / `tts`）的连接配置：`provider_id` + `kind` 唯一、api_base、full_url、protocol、api_key（`enc:` AES-GCM） |
| `model_profiles` | settings | 按能力声明的模型条目：`provider_id` + `model` 唯一，cap_chat / cap_vision / cap_audio_in / cap_audio_out / cap_reasoning |
| `task_bindings` | settings | 按任务的默认模型绑定：`task` 唯一、profile_id、fallback_handler、fallback_mode |
| `integration_credentials` | settings | 第三方密钥（GitHub PAT）：`key` 唯一、secret_enc（AES-GCM） |
| `llm_settings` | settings（legacy） | 单行宽表；legacy→`stage_configs` 一次性导入的数据源——该导入以本表存在为触发条件（`platform/services/pipeline/legacy.py`），其余场景不读取 |

### sessions.db — 挂载于 `SessionsBase`

| 表 | 域 | 用途（关键列） |
| --- | --- | --- |
| `rate_limit_buckets` | platform | 限流桶（共享表后端） |
| `prep_sessions` | prep | 备面教练会话：target_role、target_company、messages、token_usage、prompt / completion / cached tokens、status、access_token、linked_session_id、summary、message_count |
| `prep_memories` | prep | 长期备面记忆：用户标记轮次、要点、agent 笔记 |
| `interview_sessions` | interview | 进行中的面试间状态：role / level / company、workflow_type、status、current_phase、agent_state、messages、ledger、report、overall_score、process_id、round_no、result、plan |
| `interview_processes` | interview | 多轮面试流程，会话经 process_id 挂在其下：max_rounds、current_round、round_plan、round_plan_status、流程记忆 |
| `ws_session_leases` | interview | 每会话仅一条活跃 WS 租约：`session_id` 唯一、lease_token |
| `company_briefs` | interview | 公司 / 岗位 / 级别 / 面试类型的缓存简报：`company_key` 唯一 |
| `interview_reports` | records | 每会话一份复盘报告：`session_id` 唯一、status、payload、model_meta |
| `growth_records` | growth | 每会话的成长快照：`session_id` 唯一、weak_skills、common_mistakes、training_plan |

## 运行时数据位置

全部运行时状态位于 `apps/api/src/realmock/platform/data/`（gitignored，`stt_fixtures/` 除外）：

| 路径 | 内容 |
| --- | --- |
| `api.db`（+ `-wal` / `-shm`） | 档案 / 配置库 |
| `sessions.db`（+ `-wal` / `-shm`） | 会话 / 运行时库 |
| `chroma/` | 本地 RAG（Chroma）持久化 |
| `system_learning.json`（+ `.lock`） | 成长域系统学习状态 |
| `.secret.key` | 未设置 `SECRET_KEY` 时自动生成的主密钥 |
| `stt_fixtures/` | 已跟踪的测试数据（唯一被跟踪的条目） |

用户上传文件写入 `platform/uploads/`（`Settings.upload_dir`），同样不纳入版本控制。

## SQLite PRAGMA

文件型 SQLite 引擎在连接时设置以下 PRAGMA（`platform/database.py: _sqlite_pragmas`）：

| PRAGMA | 值 |
| --- | --- |
| `journal_mode` | `WAL` |
| `busy_timeout` | `5000` |
| `synchronous` | `NORMAL` |
| `foreign_keys` | `ON` |
