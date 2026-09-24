# resume/services/

resume 域业务逻辑:摄取、深度评价、市场分析、渲染、存储。

## 摄取与解析

| 模块 | 用途 |
| --- | --- |
| `ingest.py` | 上传流水线:落盘、抽取、解析、持久化(不 import FastAPI) |
| `text_extract.py` | 目录资源限额下的纯文本抽取 |
| `extract.py` | 抽取编排(含图片型 PDF 的视觉兜底) |
| `parser.py` | AI 转写与结构化解析 |
| `render.py` | 确定性 PDF 页 → PNG(预览与视觉兜底图) |

## 深度评价

| 模块 | 用途 |
| --- | --- |
| `analysis.py` | 评价编排:文本自愈 → agent 循环 → 持久化 |
| `review_context.py` | 评价 agent 的 DB 输入构建 |
| `analysis_prompt.py` | 评价 system prompt 与共享 JSON schema 文本 |
| `sites.py` | 市场搜索的站点白名单 |
| `repo_evidence.py` | GitHub 仓库取证 |
| `analysis_normalize.py` | 评价载荷归一化 |
| `score_anchor.py` | 复评校准用的历史分数参照 |
| `analyze_slots.py` | 进程内并发上限(满载抛 A1007) |

## 存储与契约

| 模块 | 用途 |
| --- | --- |
| `store.py` | 持久化:行、家族、磁盘文件 |
| `files.py` | 已存上传文件的磁盘查找 |
| `resume_versions.py` | 版本血缘:家族身份、带分历史 |
| `resume_mappers.py` | 宽容 JSON 强转与 API 响应组装 |
| `contract_guard.py` | 契约 ↔ ORM / catalog 漂移守卫(import 时即失败) |

组合这些服务的 agent 在 `../agents`。
