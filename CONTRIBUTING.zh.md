# 贡献指南

RealMock 是个人本地优先项目。本指南描述日常开发方式与
CI 的确切要求；agent 相关工作规则见 [AGENTS.md](AGENTS.md)。

## 环境准备

- 后端：Python 3.14（`requires-python >=3.14`）—— 建项目 venv 并可编辑安装：`uv venv && uv pip install -e 'apps/api[dev]'`（测试依赖在 `dev` extra；运行时镜像无需 extra）。后端服务同样从该 venv 启动（`scripts/dev.sh`）
- 前端：Node 24（见 [.nvmrc](.nvmrc)）—— 在 `apps/web` 内 `npm ci`
- 一键本地开发：`scripts/dev.sh start|stop`（前端 8080，后端 8081，日志与 PID 在 `logs/`）

## 检查项（本地必须与 CI 一致）

除注明外均在 `apps/api` 下运行：

| 门禁 | 命令 | 说明 |
|---|---|---|
| Lint | `python -m ruff check apps/api` | 在仓库根目录运行；CI 钉 `ruff==0.16.10` |
| 类型 | `python -m mypy src` | CI 钉 `mypy==2.4.0`；阻塞门，必须保持 0 错误 |
| 测试 | `python -m pytest` | CI 对整个 `realmock` 包有 >=90% 覆盖率门（`--cov=realmock`） |
| 依赖审计 | `pip-audit --ignore-vuln PYSEC-2026-311 --ignore-vuln PYSEC-2026-3813 --ignore-vuln PYSEC-2026-3814 --ignore-vuln PYSEC-2026-3815` | chromadb 1.5.9 已知问题且上游无修复版；已在 `pyproject.toml` 声明 |
| 依赖政策 | `python scripts/ci/check_python_deps_policy.py` | 在仓库根目录运行；禁用包清单在 `scripts/ci/dependency-policy.json`（扫描已安装环境，含传递依赖） |

前端，在 `apps/web` 下运行：

```bash
npx tsc --noEmit   # 类型检查
npm run lint       # eslint
npm test           # vitest(覆盖率阈值由 apps/web/vitest.config.mts 强制)
npm run build      # 生产构建
npm run audit      # 依赖审计（high+ 未列入 npm-audit-allowlist.json 则失败）
node scripts/check-i18n-usage.mjs                               # 幽灵键 + 死键（豁免清单：i18n-usage-allowlist.json）
node ../../scripts/ci/check_npm_deps_policy.mjs                 # 禁用包（scripts/ci/dependency-policy.json）
```

## Git 钩子（可选）

仓库自带一个只查暂存文件的快速钩子（ruff + prettier，对齐两道格式门）。
每个克隆启用一次：

```bash
git config core.hooksPath .githooks
```

其余门禁刻意留在 CI——钩子是便利，不是门。

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

## 安全

漏洞请按 [SECURITY.zh.md](SECURITY.zh.md) 私下报告——不要提公开 issue。
其中列出了安全相关面及其防护;触碰这些路径的改动在评审时需要额外审慎。

## 文档

每份文档配中文镜像（`<name>.zh.md`）并与代码保持同步；目录内文件名不再
自解释时补 README。两项不变量均由 CI 强制：`scripts/ci/check_docs_pairs.py`
对未配对页面报错，lychee（离线模式）对失效内链报错。
