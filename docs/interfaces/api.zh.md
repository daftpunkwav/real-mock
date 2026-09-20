# RealMock HTTP API

FastAPI 聚合应用（`realmock.asgi:app`）将七个业务域路由挂载在 `/api/v1` 下，并注册 `/api` 作为滚动兼容别名。完整机器可读契约为仓库根的 [`openapi.json`](../../openapi.json)。

## 挂载与访问控制

| 维度 | 行为 |
| --- | --- |
| 挂载 | `platform/router_mount.py: include_with_legacy_api_alias()` 将每个域的 `service_router` 挂载到 `/api/v1`，并再次挂载到 `/api` |
| 域内前缀 | 由各域 router 自持（`domains/<name>/router.py`）：`/profile`、`/resume`、`/settings`、`/prep`、`/interview`、`/options`、`/records`、`/reports`、`/growth` |
| 本地访问 | `platform/core/local_only.py: LOCAL_API_DEPENDENCIES` 在挂载层应用于所有 HTTP 路由：`require_local_peer`（仅允许回环地址，否则 `A0405`）+ `reject_cross_site_fetch`（拒绝浏览器 `Sec-Fetch-Site: cross-site` 请求，`A0403`）+ `require_same_origin_for_writes`（非安全方法要求白名单内 `Origin`/`Referer`，`A0403`） |
| 能力令牌 | interview / prep / report 的内容读取路由另需会话能力令牌（`platform/core/session_auth/extract.py`）：header `X-Interview-Token` > cookie > query `token=`（仅非生产环境） |
| WebSocket | FastAPI 依赖不作用于 WS scope；`ws/interview` 在路由体内执行 origin + 令牌检查 — 见 [realtime-protocol.zh.md](realtime-protocol.zh.md) |
| 健康检查 | `GET /health`（直接注册在应用上，不在 `/api` 前缀内） |

## 契约链

`scripts/export_openapi.py` → 根 `openapi.json` → `apps/web/src/types/generated/api.d.ts`（执行 `cd apps/web && npm run generate:api-types`）。守卫：`apps/api/tests/architecture/test_api_v1_paths.py`（两个前缀同时存在）与 `test_openapi_contract_sync.py`（仓库内的 `openapi.json` 与应用实时 schema 一致）。

## 各域端点

以下路径相对 `/api/v1`；每个路径在 `/api` 别名下同样存在。

### profile — `domains/profile/routes/profile.py`

| 方法 | 路径 | 端点组 |
| --- | --- | --- |
| GET / PUT | `/profile` | 单行画像：读取 / 全量替换更新 |
| POST | `/profile/clear` | 清空所有可更新字段 |

### resume — `domains/resume/routes/`（`router.py` 聚合 `upload` / `crud` / `file` / `analyze`）

| 方法 | 路径 | 端点组 |
| --- | --- | --- |
| POST | `/resume/upload`、`/resume/{resume_id}/versions` | 上传 / 新增版本 |
| GET | `/resume/limits`、`/resume/list`、`/resume/{resume_id}` | 限额、列表、单份简历 |
| POST | `/resume/{resume_id}/activate` | 设为生效简历 |
| DELETE | `/resume/{resume_id}`、`/resume/analyses`、`/resume/collection` | 删除单份 / 清空复盘结果 / 删除全部 |
| GET | `/resume/{resume_id}/file`、`/resume/{resume_id}/pages`、`/resume/{resume_id}/pages/{page_no}` | 文件下载与分页页面图片 |
| POST | `/resume/{resume_id}/analyze`、`/resume/{resume_id}/analyze/stream` | 深度复盘（JSON / SSE） |

### settings — `domains/settings/routes/`（`models` / `stages` / `model_tests` / `integrations`）

| 方法 | 路径 | 端点组 |
| --- | --- | --- |
| GET | `/settings/models`、`/settings/providers`、`/settings/vendors`、`/settings/bindings` | 目录与当前配置 |
| POST | `/settings/vendors/{vendor_id}/apply` | 供应商一键开通(按描述符创建 provider + models + channels) |
| POST / PUT / DELETE | `/settings/providers`、`/settings/providers/{provider_id}`、`/settings/providers/{provider_id}/models`、`/settings/models/{model_id}` | 供应商与模型 CRUD |
| PUT / GET | `/settings/providers/{provider_id}/channels/{kind}`、`.../catalog` | 渠道配置与目录 |
| PUT | `/settings/bindings/{task}` | 任务到模型的绑定 |
| GET / PUT | `/settings/stages`、`/settings/stages/{stage}` | 阶段配置（recognize / reason / speak） |
| GET | `/settings/catalog` | 阶段目录 |
| POST | `/settings/test/{stage}`、`/settings/test/model/{model_id}` | 连通性测试 |
| GET / POST / DELETE | `/settings/integrations/github` | GitHub 绑定 |
| POST | `/settings/integrations/github/test` | GitHub 绑定测试 |

### prep — `domains/prep/routes/`（`router.py` 挂载 `lists` / `create` / `chat` / `history` / `manage` / `memories`）

| 方法 | 路径 | 端点组 |
| --- | --- | --- |
| GET | `/prep/resumes`、`/prep/sessions` | 列表 |
| POST | `/prep/sessions` | 创建会话（写入能力 cookie） |
| POST | `/prep/sessions/{session_id}/message`、`/prep/sessions/{session_id}/message/stream` | 对话轮次（JSON / SSE） |
| GET | `/prep/sessions/{session_id}/messages`、`/prep/sessions/{session_id}/context` | 历史与上下文 |
| POST | `/prep/sessions/{session_id}/compact`、`/prep/sessions/{session_id}/fork`、`/prep/sessions/{session_id}/messages/truncate` | 历史操作 |
| PATCH | `/prep/sessions/{session_id}/summary` | 更新滚动摘要 |
| DELETE | `/prep/sessions/{session_id}` | 删除会话 |
| POST | `/prep/sessions/purge-empty`、`/prep/sessions/purge-all` | 批量清理 |
| PATCH / PUT / POST | `/prep/sessions/{session_id}/archive`、`/prep/sessions/{session_id}/link`、`/prep/sessions/{session_id}/reissue` | 归档 / 关联简历 / 重发令牌 |
| GET / POST | `/prep/memories`、`/prep/memories/tags`、`/prep/memories/batch-delete` | 长期记忆 |
| GET / PATCH / DELETE | `/prep/memories/{memory_id}` | 记忆条目 |

内容读取路由（message / stream / messages / fork / context）要求能力令牌；所有者级路由改用同源 CSRF 保护。

### interview — `domains/interview/routes/`（`interview.py` 挂载 `sessions` / `turns` / `processes`；另有 `brief.py`、`options.py`、`ws/`）

| 方法 | 路径 | 端点组 |
| --- | --- | --- |
| GET | `/interview/resumes` | 简历选择器 |
| POST / GET | `/interview/sessions` | 创建 / 列出独立面试会话 |
| GET | `/interview/sessions/{session_id}`、`/interview/sessions/{session_id}/messages` | 会话详情与消息 |
| POST | `/interview/sessions/{session_id}/start`、`/interview/sessions/{session_id}/message`、`/interview/sessions/{session_id}/finish` | HTTP 轮次 API（面试间本体运行在 WebSocket 上） |
| POST / GET | `/interview/processes` | 创建（连同 round-1 会话）/ 列出多轮面试流程 |
| GET | `/interview/processes/{process_id}` | 流程详情（轮次链、轮次计划） |
| POST | `/interview/processes/{process_id}/rounds` | 创建下一轮 — 见 [interview-flow.zh.md](../interview-flow.zh.md) |
| POST / DELETE | `/interview/company-brief`、`/interview/company-briefs` | 公司调研简报 |
| GET | `/options` | 设置页选项（工作流 / 面试官风格 / 音色 / 形象） |
| WS | `/ws/interview/{session_id}` | 实时面试间 — 见 [realtime-protocol.zh.md](realtime-protocol.zh.md) |

### records — `domains/records/routes/`（`history` / `report`）

| 方法 | 路径 | 端点组 |
| --- | --- | --- |
| GET | `/records/sessions` | 面试历史 |
| GET | `/records/sessions/{session_id}/ledger` | 冻结的会话台账 |
| GET | `/reports/{session_id}` | 复盘报告（pending / generating 返回 `A2004`，failed 返回 `A2005`） |
| POST | `/reports/{session_id}/retry` | 重新排队报告生成（幂等） |
| GET | `/reports/{session_id}/stream` | 伪流式报告（pending 时生成一次） |

### growth — `domains/growth/routes/router.py`

| 方法 | 路径 | 端点组 |
| --- | --- | --- |
| GET | `/growth/history` | 面试历史统计 |
| GET | `/growth/system-insights` | 系统洞察报告 |
| GET | `/growth/aggregated` | 成长聚合视图 |
