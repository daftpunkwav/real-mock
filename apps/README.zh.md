# apps/

可部署应用。每个子目录是自带工具链与 README 的独立应用。

| 目录 | 应用 | 角色 |
| --- | --- | --- |
| [`web/`](web/README.zh.md) | RealMock web | Next.js + React 前端(dev server 端口 8080) |
| [`api/`](api/README.zh.md) | RealMock API | FastAPI 后端,以 `realmock` 包发布(端口 8081) |

本地开发中两个应用并行运行:在仓库根目录执行 `scripts/dev.sh start` 以后台进程方式启动两者。
