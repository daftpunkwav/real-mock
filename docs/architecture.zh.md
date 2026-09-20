# RealMock 架构

后端是一个模块化单体：单 FastAPI 进程，以 `realmock` 包（src layout）形式打包在 `apps/api/` 下，在 `src/realmock/asgi.py` 中组装。

## 分层

| 包 | 职责 | 可依赖 |
| --- | --- | --- |
| `platform/` | 平台内核：跨域基础设施（AI / 语音能力、DB、配置、contracts、共享服务） | 仅 `platform` |
| `domains/` | 七个业务域 | `platform` + 自身包；绝不依赖其他域 |
| `bootstrap/` | 组合根：数据库装配（`db_bootstrap.py`）与 sessions ORM（`sessions_orm.py`） | `platform` + `domains` |

`bootstrap/` 位于 `platform/` 之外，因为它需要导入各域包，在建表前注册其 ORM 模型；platform 到 domain 的导入属于架构违规（由 `tests/architecture/test_platform_no_domain_imports.py` 守护）。

## 业务域

| 域 | 职责 |
| --- | --- |
| `profile/` | 候选人画像（单租户；PUT 全量替换语义） |
| `resume/` | 简历上传、解析、深度复盘、分页预览 |
| `settings/` | 供应商 / 模型 / 阶段设置与集成（GitHub 绑定、模型测试） |
| `prep/` | 备面教练：带工具的 agent 对话、记忆压缩、用量统计 |
| `interview/` | 拟真面试间：实时 WebSocket、多轮流程、裁定 |
| `records/` | 面试历史与复盘报告 |
| `growth/` | 成长统计 |

每个域导出一个 `service_router`（`domains/<name>/router.py`），路径前缀由域自持（如 `/profile`、`/resume`、`/settings`、`/prep`、`/interview`、`/options`、`/records`、`/reports`、`/growth`）。

## 依赖规则与守卫

依赖方向：`bootstrap/` -> `domains/` -> `platform/`；跨域协作经由 platform 服务与 contracts。规则由 `apps/api/tests/architecture/` 下的测试套件强制执行：

| 测试 | 守护内容 |
| --- | --- |
| `test_platform_no_domain_imports.py` | AST 守卫：`platform` 不得导入 `realmock.domains` 或 `realmock.bootstrap` |
| `test_domains_no_cross_imports.py` | AST 守卫：域之间不得相互导入 |
| `test_db_boundary_imports.py` | interview / agent 域不得直接导入共享表（api.db）ORM 模型 |
| `test_bootstrap_session_domains.py` | 独立进程不得加载无关业务 ORM |
| `test_interview_layering.py` | interview 域内分层的 AST 守卫 |
| `test_api_v1_paths.py` | `/api/v1` 与 `/api` 兼容别名同时存在 |
| `test_app_factory.py` | `app_factory` / `asgi` 入口与中间件行为 |
| `test_exposure_guards.py` | 部署暴露面守卫回归 |
| `test_openapi_contract_sync.py` | 仓库内 `openapi.json` 与应用实时 schema 一致 |

## 域内分层惯例

各域共享一套分层；域只保留自己需要的层：

| 层 | 职责 |
| --- | --- |
| `router.py` | 组装并导出域的 `service_router` |
| `routes/` | HTTP / WS 端点（薄层：解析、委托、序列化） |
| `services/` | 业务逻辑 |
| `agents/` | LLM agent（agent 驱动的域） |
| `schemas/` | 请求 / 响应 pydantic 模型 |
| `models/` | 域 ORM 模型（拥有 sessions.db 表的域） |
| `main.py` / `startup.py` | 域生命周期钩子（按需） |
| `column_migrations.py` | 域表的轻量列级迁移 |

`interview/` 额外携带 `realtime/`（WebSocket 运行时）、`process/`（多轮流程编排与轮次摘要）、`protocols/`（plan / round-plan schema、轮次链、流程记忆）、`capabilities/`（RAG、编码沙箱、视觉）、`ledger/`（追加 / 冻结的会话台账）以及域根的 `workflows.py`（阶段 / 工作流定义，由测试与前端 `apps/web/src/config/phases.ts` 锁定）。

## 进程组装

`asgi.py` 构建聚合应用：

| 步骤 | 模块 | 职责 |
| --- | --- | --- |
| 1 | `asgi.create_app()` | 日志、配置、`FastAPI(title="RealMock API")` |
| 2 | `platform/app_factory.py` | `install_trace_middleware`、`add_default_cors`、`register_core_error_handlers`；CORS 与 secret key 策略检查在 `asgi.py` 中执行 |
| 3 | `platform/router_mount.py` | `include_with_legacy_api_alias` 将七个域 router 挂载到 `/api/v1`，并注册 legacy `/api` 别名 |
| 4 | lifespan | `bootstrap/db_bootstrap.py`：`bootstrap_databases_and_seed()`（建表、迁移、种子数据）与 platform contract 接线；随后 `domains/interview/startup.py: ensure_rag_index()` |

`platform/app_factory.py` 还提供 `create_service_app()`，供独立域入口 `domains/prep/main.py` 与 `domains/interview/main.py` 使用（CORS、`/health`、`/api/v1` 前缀、异常处理器、trace 中间件）。聚合入口有自己的一套组装，不复用该工厂。

## 前端

`apps/web/` 为 Next.js + React 前端（开发服务器运行于 8080 端口）。见 [apps/web/README.md](../apps/web/README.md)。
