# records/agents/report/

两阶段 ReAct 流水线,从冻结的会话 ledger 产出深度面试报告。上层地图见
[../../..](../../../README.zh.md)(records 域)。

## 流水线

| 模块 | 职责 |
| --- | --- |
| `agent.py` | `DeepReportAgent` 编排:批次切分(`TURNS_PER_BATCH`)、有界并行的阶段一(`MAX_PARALLEL_BATCHES`)、总时长预算 `REPORT_TIME_BUDGET_SECONDS`、上下文 specs |
| `turn_notes_agent.py` | 阶段一:每批对话轮一个 ReAct 循环;各自读取、思考、核验,最后为每轮产出一条深度笔记;覆盖缺口触发重试路径 |
| `synthesis_agent.py` | 阶段二:一个 ReAct 循环经分页工具读取全部笔记,对存疑笔记回查 ledger 抽查,然后写出 verdict、分数明细、亮点/关键问题与训练计划 |

## 支撑模块

| 模块 | 职责 |
| --- | --- |
| `ledger_tools.py` | 冻结转录的渐进式披露:`ledger_overview` / `ledger_read_turns` / `ledger_search` 按有界页拉取;批次运行把读取限制在自己的轮次范围——转录绝不一次性塞进 prompt |
| `prompts.py` | 两个阶段的系统提示词与 JSON 契约 |
| `finalize.py` | agent 输出的 JSON 提取与有据修复;有界 LLM 修复是失败前最后一道兜底 |
| `normalize.py` | 容错归一化为 schema 类型(别名、钳位、列表上限),单个漂移字段不拖垮整份报告 |

测试:`apps/api/tests/records/`。
