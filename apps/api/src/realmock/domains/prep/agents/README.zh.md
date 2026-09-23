# prep/agents/

Prep agent 机制:think-then-act 循环与一个 prep 轮次触及的一切。

| 模块 | 用途 |
| --- | --- |
| `chat.py` | 轮次编排:同步单轮与事件流式回答 |
| `agent.py` | prep agent 本体(函数调用 think-then-act 循环) |
| `turn_tools.py` | 每轮工具集策略 |
| `tool_exec.py` | 工具执行回调:ask_user 分发、相同参数短路、每工具默认超时(模型可按次覆盖)、瞬态失败自动重试、失败观测携带熔断计数 |
| `turn_state.py` | 每轮可变状态 |
| `round_compaction.py` | 轮内上下文压缩 |
| `streaming.py` | 投机内容 token、工具轮事件队列、提前输出 |
| `persist.py` | 轮次持久化:压缩事件、消息定稿、用量增量与请求诊断 |
| `memory_precipitate.py` | 轮末记忆沉淀:一次咨询式 LLM 调用判定本 turn 是否值得存入长期记忆;至多写一条,绝不抛错 |
| `quiz_render.py` | 内联 quiz 的工具调用漂移渲染 |

| 子包 | 用途 |
| --- | --- |
| `context/` | 上下文装配:`seed.py`(稳定优先的种子块)、`working.py`、`linked.py`(# 引用的会话)、`hints.py`、`markers.py` |
| `ask_user/` | 用户提问控制流:`dispatch.py`、`inline.py`、`normalize.py`、`schema.py` |
| [`tools/`](tools/README.zh.md) | 工具注册表(`registry.py`、`spec.py`)与五个工具族:`basic/`(code_exec、company_info、quiz、take_note、web_search、web_fetch)、`candidate/`(profile、resume、shared)、`memory/`(write、list_summaries、get_detail、list_tags)、`repo/`(github)、`system/`(availability、compact、search_tools) |
