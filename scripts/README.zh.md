# scripts/

仓库级开发与代码生成脚本。

| 脚本 | 用途 |
| --- | --- |
| `dev.sh` | 一键本地启动:`start` / `stop` 以后台进程方式启动或停止前端与后端;日志与 PID 在 `logs/` |
| `export_openapi.py` | 将 FastAPI 应用的 OpenAPI schema 导出到根目录 `openapi.json` — 契约流水线前半段;后半段是 `apps/web` 的 `npm run generate:api-types` |
