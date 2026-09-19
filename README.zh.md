# RealMock

AI 模拟面试应用:上传简历获得解析与深度评价,通过 Prep 面试教练备赛,再进入拟真面试房进行实时问答(含语音)。前端 Next.js + React,后端 Python 模块化单体(FastAPI)。

## 目录结构

| 目录 | 用途 |
| --- | --- |
| [`apps/`](apps/README.zh.md) | 可部署应用 — 见各应用 README |
| [`apps/web`](apps/web/README.zh.md) | 前端(Next.js,dev 模式运行于 8080 端口) |
| [`apps/api`](apps/api/README.zh.md) | 后端(FastAPI,端口 8081):`realmock` 包(src layout);`platform`(平台内核)/ `domains`(七个域:profile / resume / settings / prep / interview / records / growth),由 `realmock.asgi` 聚合为单进程;测试位于 [`apps/api/tests`](apps/api/tests/README.zh.md) |
| [`scripts/`](scripts/README.zh.md) | 开发与生成脚本(`dev.sh`、`export_openapi.py`) |
| [`protocol/`](protocol/README.zh.md) | WebSocket 消息协议 schema(`interview_ws.schema.json`) |
| `logs/` | 运行日志(由 `dev.sh` 创建和写入) |

## 本地开发

```bash
# 一条命令启动前端 + 后端(后台运行;日志在 logs/,PID 在 logs/*.pid)
scripts/dev.sh start

# 停止
scripts/dev.sh stop
```

手动启动:

```bash
# 后端:先以 editable 方式安装一次,之后按包名启动(无需 PYTHONPATH)
pip install -e ./apps/api
python -m uvicorn realmock.asgi:app --host 127.0.0.1 --port 8081

# 前端:必须保持 dev 模式
cd apps/web && npm run dev
```

深度评价并发上限(3)按**进程**计,不跨进程共享。`uvicorn --workers N` 时总并发约为 N×3。本地开发保持单 worker。

## 测试与契约

```bash
cd apps/api && pytest    # 后端测试(testpaths = tests,按域 / 分层组织)
cd apps/web && npm test  # 前端测试(vitest)
```

API 契约流水线:`scripts/export_openapi.py` → 根目录 `openapi.json` → `apps/web/src/types/generated/api.d.ts`(`cd apps/web && npm run generate:api-types`)。

## 许可证

[MIT](LICENSE)
