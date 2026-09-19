# resume/

简历域:上传、解析、深度评价、服务端分页预览。

| 层 | 内容 |
| --- | --- |
| `routes/` | `upload.py` / `crud.py` / `file.py`(上传、CRUD、预览)与 `analyze.py`(深度评价:JSON `POST /analyze` 加 SSE `/analyze/stream`,实时输出 plan / tool / thinking 事件) |
| [`services/`](services/README.zh.md) | 摄取流水线(`ingest.py`:落盘、文本抽取、LLM 解析、持久化)、分析(`analysis*.py`、`market_*.py`、`sites.py`、`repo_evidence.py`、`score_anchor.py`)、渲染(`render.py`:确定性 PDF 页 → PNG,用于预览与视觉兜底)、槽位上限(`analyze_slots.py`)、存储(`store.py`、`files.py`、`resume_versions.py`) |
| `agents/` | `review.py`(评价 agent:工具循环、JSON 收束、事件回调)与 `process.py`(评价计划工具:模型自持 8–15 步清单,前端渲染为实时进度) |
| `schemas/` | `limits.py`(`MAX_PARALLEL_ANALYZE = 3`)、`request.py` / `response.py` / `analysis.py` / `resume.py` / `locale.py` |

说明:

- 深度评价并发上限按进程计;满载立即抛 A1007(不排队)。本地保持单 worker。
- 图片型 PDF 兜底为视觉转写:`render.py` 提供页面图片,抽取环节消费。

测试:`apps/api/tests/resume/`。
