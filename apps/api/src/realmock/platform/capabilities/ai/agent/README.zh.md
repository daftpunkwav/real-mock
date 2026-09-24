# capabilities/ai/agent/

共享 agent 内核:think-then-act 循环、工作记忆与工具注册表。interviewer 与
prep agent 都跑在本包上;域特定的工具留在各自域内。上层地图见
[../README.zh.md](../README.zh.md)。

## 循环内核

| 模块 | 职责 |
| --- | --- |
| `loop.py` | `run_agent_loop`:一步 = 一次 LLM 调用 + 本轮工具执行。域工具注册 OpenAI tools schema 加一个 `execute` 回调;不引入 MCP、shell 或子 agent。瞬态单请求后缀:日期时间锚点、预算行(轮数/宽度/已消耗);被输出上限截断的最终答案自动无缝续写一次;末轮可整体省略 tools 参数(`final_round_tool_free`),让轮次上限产出真实回答 |
| `llm_round.py` | 单轮 LLM 调用:优先流式、非流式兜底,超长工具结果截断 |
| `events.py` | 进度事件契约(`AgentEvent`、`OnAgentEvent`);发射有守卫,UI 回调失败不会打断循环 |
| `halt.py` | `AgentHalt`:工具请求立即终止循环(如 `ask_user` 等待用户输入) |
| `hints.py` | 轮次预算感知:仅在最后一轮注入收尾提示,让模型收束而不是被硬截断 |
| `working_memory.py` | 压缩后仍保留在模型可见上下文中的结构化事实——会话记忆与逐字对话分离 |

## `tools/` — 可组合工具注册表

| 模块 | 职责 |
| --- | --- |
| `spec.py` | `ToolSpec`(JSON schema + 异步 execute)与运行时分发器 `ToolBundle`;各域自行组装工具集,互不导入 |
| `executor.py` | 单次工具调用的超时 + 错误分类包装;统一结果契约 `(raw, status)`,`done` / `error` |
| `codeexec.py` | 供 agent 自证的沙箱代码执行;隔离后端在 [`tools/isolation/`](tools/isolation/)(默认 `process.py`,Linux 上 `linux_job.py`) |
| `fetch.py` | 经 SSRF 校验的 pinned client 出站网页抓取 |
| `search.py` | 联网搜索工具 |
| `github.py` | GitHub 查询,走 `platform/capabilities/integrations/github/`;返回的 spec 深拷贝共享定义,消费方可自由改写自己的参数 |
| `profile.py` / `resume.py` | 候选人上下文工具:对调用方传入的 profile/resume payload 做分级抽检 |

测试:`apps/api/tests/platform_ai/`。
