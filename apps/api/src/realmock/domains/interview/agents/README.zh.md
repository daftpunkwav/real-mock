# interview/agents/

interview 域的 LLM 角色:一角色一子包,共享机制平铺在包根。包 `__init__` 即**门面** — `realtime` / `routes` / `process` 仅依赖门面加两个叶子契约 `agents.events` 与 `agents.agent_text`,禁止依赖兄弟模块。

## 角色子包

| 子包 | 用途 |
| --- | --- |
| `interviewer/` | 主面试官:`runner.py` 加 `runner_opening.py` / `runner_turn.py` / `runner_closing.py` |
| `topology/` | 影子评估 agent:三段式后台评估 —— 评估、复核(仅当首轮自报 `evidence_insufficient`)、追问合成;grounding 全量逐字注入,无工具,预算 90 秒(`agent_policies.BACKGROUND`) |
| `hint/` | 参考答案 agent(`hint_answer.py`):默认零工具、全量 grounding 直填;问题命中 GitHub 信号时升级为 github-only 的 2 轮循环 |
| `planning/` | 流程规划与轮次规划(`planner.py`、`round_planner.py` 及各自提示词模块) |
| `research/` | 公司联网调研与配置页 brief(`company_research.py`、`company_brief.py`) |
| `memory/` | 认知记忆图 |

## 平铺内核

内部模块按子模块路径互相 import,按前缀分簇:

| 簇 | 模块 |
| --- | --- |
| protocol | `events`、`agent_text`、`turn_output`、`say_first` |
| state | `session_state`、`session_overrides`、`past_records`、`history_compaction` |
| compaction | `step_compaction`(拼接+编排)、`step_compaction_state`(状态簿记)、`step_compaction_summary`(转写→简报)、`step_compaction_prompts` |
| prompts | `agent_prompts`、`closing_prompts`、`prompt_assembler`、`session_prompt` |
| policy | `agent_policies` |
| rounds | `tool_round_runner`、`tool_round_stream`、`tools`、`tool_guard` |
| turn | `followup`、`followup_inject`、`finish_lifecycle` |

相关轮次状态机与媒体管线在 [`../realtime`](../realtime/README.zh.md);阶段 SSOT 在 `../workflows.py`。
