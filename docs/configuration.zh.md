# RealMock 配置

后端配置位于 `apps/api/src/realmock/platform/config.py`（`Settings`，pydantic-settings）。环境变量使用无前缀的字段名；取值也可来自 `apps/api/src/realmock/platform/.env`（`PLATFORM_ROOT/.env`）。`get_settings()` 缓存单例。

## 后端设置

| 环境变量 | 字段 | 含义 | 默认值 |
| --- | --- | --- | --- |
| `ENV` | `env` | `dev` / `prod`；决定 CORS 严格程度与本地 LLM 门禁 | `dev` |
| `HOST` | `host` | 绑定地址；局域网调试设 `0.0.0.0` | `127.0.0.1` |
| `PORT` | `port` | 绑定端口 | `8081` |
| `CORS_ORIGINS` | `cors_origins` | 逗号分隔的允许来源 | `http://localhost:8080,http://127.0.0.1:8080` |
| `LLM_API_BASE` | `llm_api_base` | BYOK 对话 Base URL | `""`（空） |
| `LLM_API_KEY` | `llm_api_key` | BYOK 对话 API Key | `""`（空） |
| `LLM_MODEL` | `llm_model` | BYOK 对话模型 | `""`（空） |
| `LLM_MAX_TOKENS` | `llm_max_tokens` | 最大输出 token | `64000`（`DEFAULT_MAX_OUTPUT_TOKENS`） |
| `LLM_CONTEXT_WINDOW` | `llm_context_window` | 上下文窗口 | `256000`（`DEFAULT_CONTEXT_WINDOW`） |
| `LLM_EMBEDDINGS_BASE` | `llm_embeddings_base` | 向量 Base URL 覆盖；`None` 回退到 `llm_api_base` | `None` |
| `LLM_EMBEDDINGS_KEY` | `llm_embeddings_key` | 向量 API Key 覆盖；`None` 回退到 `llm_api_key` | `None` |
| `LLM_EMBEDDINGS_MODEL` | `llm_embeddings_model` | 向量模型覆盖；`None` 回退到 `llm_model` | `None` |
| `RAG_BACKEND` | `rag_backend` | `local` / `stepfun` / `none`（`RAGBackendKind`） | `local` |
| `STEPFUN_VECTOR_STORE_ID` | `stepfun_vector_store_id` | 复用已有 StepFun vector store；留空则启动时自动创建 | `None` |
| `API_DATABASE_URL` | `api_database_url` | api.db 连接 URL | `sqlite:///{platform}/data/api.db` |
| `SESSIONS_DATABASE_URL` | `sessions_database_url` | sessions.db 连接 URL | `sqlite:///{platform}/data/sessions.db` |
| `DATABASE_URL` | `database_url` | legacy 别名；设为非默认路径时覆盖 sessions 库 URL | `sqlite:///{platform}/data/sessions.db` |
| `UPLOAD_DIR` | `upload_dir` | 上传目录 | `{platform}/uploads` |
| `WHISPER_MODEL` | `whisper_model` | 语音识别模型；`tiny`/`base`/`small`/... 选择本地 faster-whisper | `whisper-1` |
| `TTS_VOICE` | `tts_voice` | 语音合成音色 | `zh-CN-XiaoxiaoNeural` |
| `SILENCE_NUDGE_SECONDS` | `silence_nudge_seconds` | 面试静默提醒间隔 | `10`（范围 1-600） |
| `GITHUB_TOKEN` | `github_token` | 可选 GitHub PAT（提高 API 配额） | `""`（空） |
| `INTERVIEW_TOOLS_ENABLED` | `interview_tools_enabled` | 面试 agent 是否启用 function calling 工具循环 | `True` |
| `INTERVIEW_MAX_TOOL_ROUNDS` | `interview_max_tool_rounds` | 工具循环轮数上限 | `3`（范围 0-6） |
| `ALLOW_LOCAL_LLM` | `allow_local_llm` | 是否允许本地 / 内网 `base_url` | `False` |
| `WS_LEASE_BACKEND` | `ws_lease_backend` | WS 租约存储：`memory`（单 worker）/ `database`（多 worker） | `memory` |
| `RATELIMIT_BACKEND` | `ratelimit_backend` | 限流存储：`memory` / `database` | `memory` |
| `TRUSTED_PROXY_CIDRS` | `trusted_proxy_cidrs` | 逗号分隔的可信反向代理 CIDR；为空时仅取 `request.client.host` | `""`（空） |
| `COOKIE_SECURE` | `cookie_secure` | `None` = 自动（https 或可信代理 `X-Forwarded-Proto: https`） | `None` |

## 在 `Settings` 之外读取的环境变量

| 环境变量 | 读取方 | 用途 |
| --- | --- | --- |
| `SECRET_KEY` | `platform/core/secrets.py` | 字段加密主密钥（base64 或明文，>= 16 字节） |
| `TEST_MODE` | `asgi.py`、`bootstrap/db_bootstrap.py`、`platform/app_factory.py` | `1` 切换为测试引导（conftest 临时库、不种子、不拆 legacy 单库） |
| `DATABASE_URL` | `config.py`（model validator） | legacy 覆盖，同步到 `sessions_database_url` |

## 启动时校验

| 规则 | 强制位置 |
| --- | --- |
| `env=prod` 拒绝包含 `*` 的 `CORS_ORIGINS`（dev 记录警告） | `asgi.py: _check_cors_policy` |
| `env=prod` 拒绝 `allow_local_llm=True` | `config.py` model validator |
| `env=prod` 必须提供 `SECRET_KEY`（>= 16 字节），否则启动抛错 | `asgi.py: _check_secret_key_policy` |
| `ws_lease_backend` / `ratelimit_backend` = `memory` 时记录多 worker 警告 | `bootstrap/db_bootstrap.py: _warn_inmemory_backends` |
| `rag_backend=stepfun` 且未配 `stepfun_vector_store_id` 记录警告；启动时尝试自动创建 vector store | `config.py` model validator |

## 前端变量

`apps/web/.env.example`（复制为 `.env.local`）：

| 变量 | 含义 | 示例默认值 |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE` | 后端 REST API 基地址（直连，不经 Next.js 代理） | `http://localhost:8081` |
| `NEXT_PUBLIC_WS_URL` | WebSocket 直连地址 | `ws://localhost:8081` |
| `NEXT_PUBLIC_STREAM_API_BASE` | SSE 直连地址；须与 `NEXT_PUBLIC_API_BASE` 同源 | `http://localhost:8081` |

`.env.example` 与 `config.py` 中记载的端口规划：聚合形态前端 8080 / 后端 8081；独立形态 api 8081 / agent 8082 / interview 8083。

## BYOK 模型 / 供应商配置

供应商与模型配置存储在数据库（settings 域）而非配置文件：`llm_providers`、`llm_provider_channels`、`model_profiles`、`task_bindings` 与 `stage_configs`；GitHub PAT 存于 `integration_credentials`。`Settings` 不提供默认模型——`llm_api_base` / `llm_api_key` / `llm_model` 默认为空字符串。

API Key 使用 AES-256-GCM 加密落库（`platform/core/secrets.py`）：

| 方面 | 取值 |
| --- | --- |
| 密文格式 | `enc:v2:<b64-salt16>:<b64-nonce12>:<b64-tag16>:<b64-cipher>` |
| 密钥派生 | PBKDF2-HMAC-SHA256，200000 次迭代，每条密文独立随机盐；GCM 随机 12 字节 nonce |
| 主密钥来源 | `SECRET_KEY` 环境变量；否则随机生成 32 字节密钥持久化到 `platform/data/.secret.key` |
| 旧格式密文 | `enc:v1` 抛出 `LegacySecretFormatError`；需在设置页重新保存 Key |
| 回读 | 密钥不以明文返回；列表接口仅暴露尾部掩码 |

LLM 调用的运行时解析顺序（`platform/capabilities/ai/llm/client/from_db.py`）：数据库中的 model-profile 任务绑定，其次 `stage_configs` 回退；环境变量为最后兜底。启动时，`platform/services/seed.py: seed_llm_settings()` 仅在数据库无阶段配置且环境变量提供了 Key 时，把 `LLM_*` 环境值写入 `stage_configs` 的 `reason` 阶段（Key 加密落库）。
