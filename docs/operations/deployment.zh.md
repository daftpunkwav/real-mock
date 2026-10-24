# 部署

容器镜像与 CI。工作流：[.github/workflows/ci.yml](../../.github/workflows/ci.yml)；Dockerfile：根目录 [Dockerfile](../../Dockerfile)（后端 api）与 [apps/web/Dockerfile](../../apps/web/Dockerfile)（web）。

## CI（`.github/workflows/ci.yml`）

触发：push 到 `main` 与所有 Pull Request。并发组 `ci-<ref>` 且 `cancel-in-progress: true`。`changes` job 先按 diff 分类，各领域 job 仅在对应区域有改动时执行，最后由 `gate` job 汇总结果形成唯一的必需检查项。

| Job | 运行器 / 工具链 | 步骤 |
| --- | --- | --- |
| `backend`（Backend (ruff / mypy / pytest / audit)） | ubuntu-latest，限时 20 分钟；Python 3.14，pip 缓存以 `apps/api/pyproject.toml` 为键 | 以 editable 方式安装 `apps/api` 并带上 `dev` extra（`pip install -e 'apps/api[dev]'`；该 extra 携带 pytest / pytest-asyncio 及锁定版门禁工具链 `ruff==0.16.10`、`mypy==2.4.0`、`pytest-cov==7.1.0`、`pip-audit==2.10.1`、`httpx2`）；OpenAPI 契约同步检查（`export_openapi.py` 运行后 `openapi.json` 必须无变化）；`ruff check apps/api`；`ruff format --check apps/api`；`mypy src`（阻塞）；pytest 全量回归 + 整包覆盖率门 `--cov=realmock --cov-fail-under=90` |
| `frontend`（Frontend (tsc / lint / test / build / audit)） | ubuntu-latest，限时 20 分钟；Node 24，npm 缓存以 `apps/web/package-lock.json` 为键 | `npm ci`；`npx tsc --noEmit`；`npm run lint`；`npm test`（vitest,阈值由 `apps/web/vitest.config.mts` 设定）；`npm run build`；`npm run format:check`；i18n 使用审计（`apps/web/scripts/check-i18n-usage.mjs`，幽灵键与死键） |
| `docker` | ubuntu-latest，限时 25 分钟 | 构建后端镜像（根 `Dockerfile`）与 web 镜像（`apps/web/Dockerfile`） |
| `workflow-lint` | ubuntu-latest，限时 10 分钟 | 对工作流文件自身做 lint（语法 / shellcheck，以及工作流安全审查） |
| `repo-hygiene` | ubuntu-latest，限时 5 分钟 | 仓库内文件符合 `.editorconfig`；无大小写不敏感的路径冲突；文档中英配对齐全；文档内部链接有效 |
| `gate` | ubuntu-latest，限时 5 分钟 | 唯一的必需检查项：所有实际执行的 job 均为绿则通过 |

backend job 以 job 级 env 设置 `TEST_MODE`、`ENV=dev`、`LLM_API_KEY`、`LLM_API_BASE` 与 `CORS_ORIGINS`。

依赖审计与密钥扫描不属于 `ci.yml`：它们位于 `.github/workflows/security.yml`，在 push、Pull Request 与每周定时任务时运行。

## 镜像

### 后端 api 镜像（根 `Dockerfile`，build context = 仓库根）

| 方面 | 值 |
| --- | --- |
| 基础镜像 | `python:3.14-slim`（Debian trixie） |
| 额外运行时 | 经 apt 安装 Node.js（trixie 自带 Node 20.x）——供 agent `code_exec` 工具运行 JavaScript 片段 |
| 安装 | `pip install --retries 5 --timeout 120 --index-url "$PIP_INDEX_URL" ./apps/api`（`ARG PIP_INDEX_URL` 可为弱网环境提供镜像源；retries/timeout 防止 opencv 等大 wheel 下载中断）——运行时安装，不带 `dev` extra |
| 运行用户 | `root`——agent 沙箱需经 `setpriv` / `runuser` 将片段降权到非特权用户，该机制要求 root |
| 端口 / 入口 | 8081；`uvicorn realmock.asgi:app --host 0.0.0.0 --port 8081` |
| 运行时数据 | DB / Chroma / 上传文件位于容器内 `/app/apps/api/src/realmock/platform/data`——运行时需在该路径挂载卷 |

除上表 Node.js 一行外，该 Dockerfile 有意不再安装其他 apt 包：agent 沙箱会调用 `setpriv` / `runuser` / `unshare`（trixie essential 的 util-linux 包自带）与 `nobody` 用户（来自 base-passwd）。完整沙箱强制还需镜像自身无法授予的运行时特权（如 `docker run --cap-add SYS_ADMIN` 加可写的 `/sys/fs/cgroup`）；缺省时片段仍可运行，且每个未强制的控制项都会以明确的隔离说明回报。

### Web 镜像（`apps/web/Dockerfile`，build context = `apps/web`）

| 方面 | 值 |
| --- | --- |
| 基础镜像 / 阶段 | `node:24-slim`；多阶段 `deps` → `builder` → `runner` |
| 构建参数 | `NEXT_PUBLIC_API_BASE`、`NEXT_PUBLIC_WS_URL`、`NEXT_PUBLIC_STREAM_API_BASE`——构建时注入；默认值（`http://localhost:8081`、`ws://localhost:8081`）对应单机部署；生产构建下 `env.ts` 要求三者齐全 |
| 运行用户 | `node`（官方镜像自带用户）；runner 阶段的 `COPY` 已 chown，运行期缓存写入不受影响 |
| 端口 / 入口 | 8080；`npm start -- -p 8080`，`NODE_ENV=production` |
