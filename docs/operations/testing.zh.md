# 测试

后端测试位于 `apps/api/tests/`，前端测试位于 `apps/web/src/` 中被测代码旁。

## 后端

```bash
cd apps/api && pytest
```

`testpaths = tests` 配置于 `apps/api/pyproject.toml`；目录布局镜像源码树——每域一目录，外加 platform 与横切套件。

### 领域套件

| 目录 | 覆盖 |
| --- | --- |
| `profile/` | Profile 域 |
| `resume/` | Resume 域（解析、评审管线、契约） |
| `settings/` | Settings 域 |
| `prep/` | Prep 域（agent 流、工具、记忆、压缩） |
| `interview/` | Interview 域（流程、追问、裁决） |
| `records/` | Records 域（报告 agent） |
| `growth/` | Growth 域 |

### Platform 与横切套件

| 目录 | 覆盖 |
| --- | --- |
| `platform_core/` | 平台内核（核心工具、配置、数据库） |
| `platform_ai/` | AI 能力（LLM、agent 上下文、压缩） |
| `sessions/` | 会话级集成：auth、限流、SSRF 钉扎、WS 互斥、流式 |
| `voice/` | 语音能力（voice 配置、resolve、TTS） |
| `architecture/` | 架构守卫测试 |
| `smoke/` | platform 与各域服务的聚合启动冒烟 |

### 共享夹具

| 文件 | 用途 |
| --- | --- |
| `conftest.py` | 共享 pytest fixtures |
| `fakes.py` | 共享测试替身 |

### 架构守卫测试（`tests/architecture/`）

| 文件 | 守卫内容 |
| --- | --- |
| `test_platform_no_domain_imports.py` | platform 层不得导入业务域或组合根 bootstrap 代码（AST 守卫） |
| `test_domains_no_cross_imports.py` | 域包不得导入兄弟域包（AST 守卫） |
| `test_db_boundary_imports.py` | 双库之下，interview/agent 域不得直接导入共享表 ORM 模型 |
| `test_interview_layering.py` | interview 域分层的 AST 守卫（`agents` 按 LLM 角色分子包） |
| `test_bootstrap_session_domains.py` | Bootstrap 域注册：隔离进程不得加载无关业务 ORM |
| `test_api_v1_paths.py` | `/api/v1` 与 `/api` 兼容别名均可用（`/api/v1/options` 与 `/api/options`） |
| `test_app_factory.py` | `app_factory`/`asgi` 入口与中间件行为 |
| `test_exposure_guards.py` | 部署暴露回归（local-only peer 检查；`ENV=prod` 时对非环回 peer 不得采纳 `TEST_MODE`） |
| `test_openapi_contract_sync.py` | 见下方契约守卫 |

### 契约守卫

| 测试 | 契约 |
| --- | --- |
| `tests/interview/test_phase_ssot.py` | `workflows` PhaseDef ↔ `InterviewPhaseId` ↔ 前端 `apps/web/src/config/phases.ts` |
| `tests/interview/test_ws_protocol_schema.py` | `protocol/interview_ws.schema.json` ↔ 后端 `WSClientEvent` / `WSServerEvent` ↔ 前端 `apps/web/src/types/domains/interview_ws.ts` |
| `tests/architecture/test_openapi_contract_sync.py` | 仓库根已提交的 `openapi.json` 与实时 `app.openapi()` schema 一致 |

### Realtime 测试约定

Realtime 测试 patch 所属模块的模块级符号（如 `turn.stt_finish.transcribe_utterance_result`、`voice.tts_queue.synthesize_speech`、`connection.heartbeat.verify_connection_lease`），而非 handler 类的方法。见 realtime README：`apps/api/src/realmock/domains/interview/realtime/README.md`。

## 前端

| 命令 | 用途 |
| --- | --- |
| `npm test` | vitest 单次运行 |
| `npm run test:watch` | vitest watch 模式 |
| `npx tsc --noEmit` | TypeScript 类型门 |
| `npm run lint` | ESLint |

测试放在被测代码旁的 `__tests__/` 目录中；当前规模为 `src/` 下 58 个 `*.test.ts(x)` 文件。

## CI 门禁

两个 job 在 push 到 `main` 与所有 Pull Request 时运行（`.github/workflows/ci.yml`）。

| Job | 检查 |
| --- | --- |
| `backend` | `ruff==0.15.20`；`mypy==2.1.0` 检查 `src`（阻塞）；pytest 全量回归 + 覆盖率门 `--cov-fail-under=40`，覆盖 `realmock.platform` 与 profile / resume / settings / prep / interview 五个域；`pip-audit==2.10.1` 并 `--ignore-vuln PYSEC-2026-311`（chromadb 1.5.9 已知问题，暂无修复版本） |
| `frontend` | `npm ci`；`npx tsc --noEmit`；`npm run lint`；`npm test`；`npm run build`；`npm audit --audit-level=high` |
