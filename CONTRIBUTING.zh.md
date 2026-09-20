# 贡献指南

RealMock 是个人本地优先项目。本指南描述日常开发方式与
CI 的确切要求；agent 相关工作规则见 [AGENTS.md](AGENTS.md)。

## 环境准备

- 后端：Python 3.12（CI）/ >=3.11 —— `pip install -e ./apps/api`
- 前端：Node 24（见 [.nvmrc](.nvmrc)）—— 在 `apps/web` 内 `npm ci`
- 一键本地开发：`scripts/dev.sh start|stop`（前端 8080，后端 8081，日志与 PID 在 `logs/`）

## 检查项（本地必须与 CI 一致）

除注明外均在 `apps/api` 下运行：

| 门禁 | 命令 | 说明 |
|---|---|---|
| Lint | `python -m ruff check apps/api` | CI 钉 `ruff==0.15.20` |
| 类型 | `python -m mypy src` | CI 钉 `mypy==2.1.0`；阻塞门，必须保持 0 错误 |
| 测试 | `python -m pytest` | CI 对 platform + domains 有 >=40% 覆盖率门 |
| 依赖审计 | `pip-audit --ignore-vuln PYSEC-2026-311` | chromadb 已知问题且上游无修复版；已在 `pyproject.toml` 声明 |

前端，在 `apps/web` 下运行：

```bash
npx tsc --noEmit   # 类型检查
npm run lint       # eslint
npm test           # vitest
npm run build      # 生产构建
npm run audit      # 依赖审计（high+ 未列入 npm-audit-allowlist.json 则失败）
```

## 契约与生成物

API 契约链为 `scripts/export_openapi.py` -> `openapi.json` -> `apps/web/src/types/generated/api.d.ts`。
在 `apps/web` 下用 `npm run generate:api-types` 再生成；禁止手改生成物。
契约过期时守卫测试会失败。Pydantic docstring 会泄漏进 schema 描述——用 `#`
注释而不是 docstring 来说明 schema。

## 提交与分支约定

- 提交：`<type>(<scope>): <subject>`，type 取 `feat | fix | refactor | chore | docs | test | perf`
- 提交信息用英文，只描述改动本身
- 分支：`<type>/<short-kebab-description>`，如 `feat/prep-agent-memory`

## 代码规则

评审执行，并有架构测试兜底：

- 解耦优先于内聚：混合职责即使文件很小也必须拆分；一个文件单一职责
- domains 只依赖 platform 内核——禁止跨域业务导入
- 命名保持中立，以功能、边界、职责为依据
- 注释用英文，只解释代码本身
- 最小正确 diff；不做投机性泛化
- 纯类型层改动必须零运行时足迹

## 文档

每份文档配中文镜像（`<name>.zh.md`）并与代码保持同步；目录内文件名不再
自解释时补 README。
