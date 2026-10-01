# resume/

简历域:上传、解析、深度评价、服务端分页预览。

| 层 | 内容 |
| --- | --- |
| `routes/` | `upload.py` / `crud.py` / `file.py`(上传、CRUD、预览)、`analyze.py`(深度评价:JSON `POST /analyze` 加 SSE `/analyze/stream`,实时输出 plan / tool / thinking 事件)、`parse_retry.py`(后台解析失败后的重新派发)与 `router.py`(以限流依赖挂载各 handler) |
| [`services/`](services/README.zh.md) | 摄取流水线(`ingest.py`:落盘、文本抽取、LLM 解析、持久化)、抽取与解析(`extract.py`、`text_extract.py`、`parser.py`)、分析(`analysis.py`、`analysis_normalize.py`、`review_context.py`、`sites.py`、`repo_evidence.py`、`score_anchor.py`)、渲染(`render.py`:确定性 PDF 页 → PNG,用于预览与视觉兜底)、槽位上限(`analyze_slots.py`)、存储(`store.py`、`files.py`、`resume_versions.py`)、响应组装(`resume_mappers.py`)、契约漂移守卫(`contract_guard.py`) |
| `agents/` | `review.py`(评价 agent:工具循环、事件回调)、`review_json.py`(JSON 收束:基于已收集证据的自纠错)、`review_prompts.py`(收束阶段提示、工具预算 / 熔断拒绝文案、纯文本降级提示)、`process.py`(评价计划工具:模型自持 8–15 步清单,前端渲染为实时进度)、`payload.py`(评价首条消息:视觉页面图或解析文本)与 `observe.py`(面向实时 UI 的工具观测解析) |
| `schemas/` | `limits.py`(`MAX_PARALLEL_ANALYZE = 3`)、`request.py` / `response.py` / `analysis.py` / `resume.py` / `locale.py` |

说明:

- 深度评价并发上限按进程计;满载立即抛 A1007(不排队)。本地保持单 worker。
- 图片型 PDF 兜底为视觉转写:`render.py` 提供页面图片,抽取环节消费。

测试:`apps/api/tests/resume/`。
