# capabilities/ai/

所有 agent 驱动域共享的 AI 能力层:LLM 供应商调用、通用 agent 循环、上下文窗口管理。

## [`llm/`](llm/README.zh.md) — 面向供应商的模型调用

`unified_client.py` 是协议栈 `client/` 之上的入口(OpenAI chat / Responses 与 Anthropic 协议翻译、带重试的流式、请求 / 响应组装、经 `from_db.py` 从 DB 加载供应商配置)。周边:流后处理(`stream_filters.py`、`stream_sanitizer.py`、`special_token_filter.py`)、say-first 投机流式(`say_first_stream.py`)、输出解析(`json_extract.py`、`inline_tool_call.py`、`tool_args.py`)、用量 / 默认值 / 供应商错误映射(`usage.py`、`defaults.py`、`provider_errors.py`)。

## [`agent/`](agent/README.zh.md) — 通用 think-then-act 循环

`loop.py` 驱动轮次(`llm_round.py`),配事件契约(`events.py`)、hints、终止条件(`halt.py`)与 `working_memory.py`。`tools/` 是共享工具集:spec + 执行器(`spec.py`、`executor.py`)、`github.py`、`search.py`、`fetch.py`、`profile.py`、`resume.py`、`codeexec.py`,执行隔离后端在 `tools/isolation/`(process / linux_job)。

## `context/` — 上下文窗口管理

`manager.py`(入口)、`estimation.py`(token 估算)、`compress.py` / `summarize.py`(压缩)、`blobs.py`(载荷块)、`options.py`(配置)。
