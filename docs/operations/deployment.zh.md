# 部署

容器镜像与 CI/CD。工作流：[.github/workflows/ci.yml](../../.github/workflows/ci.yml) 与 [.github/workflows/cd.yml](../../.github/workflows/cd.yml)；Dockerfile：根目录 [Dockerfile](../../Dockerfile)（后端 api）与 [apps/web/Dockerfile](../../apps/web/Dockerfile)（web）。

## CI（`.github/workflows/ci.yml`）

触发：push 到 `main` 与所有 Pull Request。并发组 `ci-<ref>` 且 `cancel-in-progress: true`；backend 与 frontend 两个 job 并行运行。

| Job | 运行器 / 工具链 | 步骤 |
| --- | --- | --- |
| `backend`（Backend (ruff / mypy / pytest / audit)） | ubuntu-latest，限时 20 分钟；Python 3.12，pip 缓存以 `apps/api/pyproject.toml` 为键 | 以 editable 方式安装 `apps/api`，并安装锁定版本 `ruff==0.15.20`、`mypy==2.1.0`、`pytest-cov==7.1.0`、`pip-audit==2.10.1`；`ruff check apps/api`；`mypy src`（阻塞）；pytest 全量回归 + 覆盖率门 `--cov-fail-under=40`，覆盖 `realmock.platform` 与 profile / resume / settings / prep / interview 五个域；`pip-audit --ignore-vuln PYSEC-2026-311`（chromadb 1.5.9 已知问题，暂无修复版本） |
| `frontend`（Frontend (tsc / lint / test / build / audit)） | ubuntu-latest，限时 20 分钟；Node 24，npm 缓存以 `apps/web/package-lock.json` 为键 | `npm ci`；`npx tsc --noEmit`；`npm run lint`；`npm test`；`npm run build`；`npm run audit`（high+ 未列入 `apps/web/npm-audit-allowlist.json` 则失败） |

backend job 以 job 级 env 设置 `TEST_MODE`、`ENV=dev`、`LLM_API_KEY`、`LLM_API_BASE` 与 `CORS_ORIGINS`。

## CD（`.github/workflows/cd.yml`）

触发：push 到 `main`（edge 标签）与 `v*` 语义化标签。认证使用内置 `GITHUB_TOKEN`（`packages: write`），无需额外 Secrets。

| 项目 | 值 |
| --- | --- |
| Job | `release` — "Build and publish images"，ubuntu-latest，限时 30 分钟 |
| Matrix | `web`：context `apps/web`，dockerfile `apps/web/Dockerfile`；`api`：context 为仓库根，dockerfile `Dockerfile` |
| 镜像仓库 | GHCR；镜像名 `ghcr.io/<repository>-web` 与 `ghcr.io/<repository>-api` |
| 标签 | 默认分支推 `edge`；`v*` 标签推 `{{version}}` 与 `{{major}}.{{minor}}`；另有 `sha-<sha>` |
| 缓存 | GitHub Actions 缓存，每组件一个 scope（`cache-from` / `cache-to type=gha`） |

## 镜像

### 后端 api 镜像（根 `Dockerfile`，build context = 仓库根）

| 方面 | 值 |
| --- | --- |
| 基础镜像 | `python:3.12-slim` |
| 额外运行时 | 经 apt 安装 Node.js（Debian bookworm 自带 Node 18.x）——供 agent `code_exec` 工具运行 JavaScript 片段 |
| 安装 | `pip install ./apps/api`（`ARG PIP_INDEX_URL` 可为弱网环境提供镜像源） |
| 端口 / 入口 | 8081；`uvicorn realmock.asgi:app --host 0.0.0.0 --port 8081` |
| 运行时数据 | DB / Chroma / 上传文件位于容器内 `/app/apps/api/src/realmock/platform/data`——运行时需在该路径挂载卷 |

除上表 Node.js 一行外，该 Dockerfile 有意不再安装其他 apt 包：agent 沙箱会调用 `setpriv` / `runuser` / `unshare`（bookworm essential 的 util-linux 包自带）与 `nobody` 用户（来自 base-passwd）。完整沙箱强制还需镜像自身无法授予的运行时特权（如 `docker run --cap-add SYS_ADMIN` 加可写的 `/sys/fs/cgroup`）；缺省时片段仍可运行，且每个未强制的控制项都会以明确的隔离说明回报。

### Web 镜像（`apps/web/Dockerfile`，build context = `apps/web`）

| 方面 | 值 |
| --- | --- |
| 基础镜像 / 阶段 | `node:24-slim`；多阶段 `deps` → `builder` → `runner` |
| 构建参数 | `NEXT_PUBLIC_API_BASE`、`NEXT_PUBLIC_WS_URL`、`NEXT_PUBLIC_STREAM_API_BASE`——构建时注入；默认值（`http://localhost:8081`、`ws://localhost:8081`）对应单机部署；生产构建下 `env.ts` 要求三者齐全 |
| 端口 / 入口 | 8080；`npm start -- -p 8080`，`NODE_ENV=production` |
