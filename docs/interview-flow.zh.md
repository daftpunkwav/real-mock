# 多轮面试流程

面试流程分两层：单个会话内的阶段工作流，以及可选的多轮流程 —— 把多个会话串成一条拟真的公司面试链。

## 阶段 / 工作流 SSOT

- 后端 SSOT：`domains/interview/workflows.py` — `PhaseDef`（id / name / description / `min_questions` / `max_questions`）；阶段 id 来自 `domains/interview/constants.py` 的 `InterviewPhaseId`。
- 前端镜像：`apps/web/src/config/phases.ts` — `PHASE_LABELS`（英文文案锁）与 `PHASE_ORDER`；UI 文案经 `interview.phase.*` i18n 命名空间本地化。
- 守卫：`apps/api/tests/interview/test_phase_ssot.py`（工作流阶段 id ↔ `InterviewPhaseId` ↔ 前端 `PHASE_ORDER` / 文案）。

## 工作流

| 工作流 id | 名称 | 阶段顺序（id，题数下限–上限） |
| --- | --- | --- |
| `technical` | Technical Interview | `identity_check` 1–1 → `self_intro` 1–1 → `basic_knowledge` 2–4 → `project_deep_dive` 3–6 → `technical_deep` 2–4 → `system_design` 1–2 → `scenario` 1–2 → `reverse_qa` 1–3 → `summary` 1–1 |
| `hr` | HR Interview | `identity_check` 1–1 → `self_intro` 1–1 → `career_plan` 2–3 → `teamwork` 2–3 → `pressure` 1–2 → `salary` 1–1 → `reverse_qa` 1–3 → `summary` 1–1 |
| `management` | Management Interview | `identity_check` 1–1 → `self_intro` 1–1 → `leadership` 2–4 → `decision_making` 2–3 → `conflict` 1–2 → `business` 2–3 → `reverse_qa` 1–3 → `summary` 1–1 |

未知工作流 id 回退到 `technical`（`get_workflow`）。

## 单会话

独立会话运行一个工作流：`POST /api/v1/interview/sessions` → `POST .../start` → `POST .../message` 轮次 → `POST .../finish`（HTTP 轮次 API；面试间本体运行在 WebSocket 上，见 [realtime-protocol.zh.md](interfaces/realtime-protocol.zh.md)）。会话从阶段 `identity_check` 起步；阶段切换以 `phase_changed` 事件推送。收尾轮由面试官 agent 宣布本轮裁定 —— `passed` / `failed`（`InterviewResult`）—— 携带在 `assistant_done.result` 上，并持久化到会话。

## 流程（多轮）

| 维度 | 行为 |
| --- | --- |
| 创建 | `POST /api/v1/interview/processes` 在一个事务里同时创建流程与 round-1 会话（`process/process_service.py: create_process_with_first_round`） |
| 轮次预算 | `max_rounds`：1–`MAX_INTERVIEW_ROUNDS`（5），默认 5（`schemas/process.py`） |
| 下一轮 | `POST /api/v1/interview/processes/{process_id}/rounds`；准入条件（`is_next_round_eligible`）：流程处于 `in_progress`、最近一轮 `completed` 且 `passed`、预算尚有剩余 |
| 状态 | `ProcessStatus`：`in_progress` / `completed` / `abandoned`；某轮 `failed`，或打满预算且通过，流程即 `completed`（`record_round_finished`） |

## 轮次规划

两个来源；HR 规划程序就绪时以其为准，否则由静态链决定（`_session_from_process`）：

- 静态链 — `protocols/round_chain.py`：每个基础工作流对应一条固定链；每个 `RoundStep` 固定该轮的 `workflow_type` / `personality` / `interview_style` / `strictness` / `focus` / `label`。轮次 kind（封闭词表，前端 i18n key 依赖它）：`tech_1`、`tech_2`、`tech_deep`、`hr_1`、`hr_2`、`mgmt`、`cross`。
- HR 规划程序 — `protocols/round_plan_schema.py`（schema `realmock.round_plan.v1`）：规划 agent 产出含 `pass_criteria` 的轮次计划；解析按字段容忍降级，结构性损坏则回退静态链。

固定链（`round_chain()`）；流程只取前 `max_rounds`（≤ 5）步，且实际使用的最后一步始终附加整场总体裁定：

| 轮次 | `technical` 基础 | `hr` 基础 | `management` 基础 |
| --- | --- | --- | --- |
| 1 | Technical Round 1（`tech_1`） | HR Round 1（`hr_1`） | Management Round 1（`mgmt`） |
| 2 | Technical Round 2（`tech_2`） | HR Round 2（`hr_2`） | Management Round 2（`mgmt`） |
| 3 | HR Round 1（`hr_1`） | Technical Round 1（`tech_1`） | HR Round 1（`hr_1`） |
| 4 | HR Round 2（`hr_2`） | Technical Round 2（`tech_2`） | HR Round 2（`hr_2`） |
| 5 | Technical Cross-check（`tech_deep`） | Management Round（`mgmt`） | Technical Round（`tech_1`） |
| 6 | Final Loop（`cross`） | HR Round 3（`hr_2`） | Executive Round（`cross`） |
| 7 | Stress Round（`tech_deep`） | Final Loop（`cross`） | HR Judgement（`hr_2`） |
| 8 | Executive Round（`cross`） | Stress Round（`tech_deep`） | Stress Round（`tech_deep`） |

每一步还带面试官画像覆盖；例如 `technical` 链第 1 轮为 `expert` / `deep_dive` / 强度 3，第 2 轮为 `expert` / `challenging` / 强度 5。

## 流程记忆（轮次摘要）

- 文档：`realmock.process_memory.v1`（`protocols/process_memory.py`）— `{schema, rounds[], final}`，存储在 `interview_processes.memory`，作为跨轮记忆供规划器与面试官 prompt 消费。
- 摘要：`process/round_digest.py: build_round_digest` — 纯规则构建，不调用 LLM；输入为面试官 agent 的结构化状态（已提问、弱点、最近一轮评分）加冻结台账的阶段覆盖。限额（`DIGEST_LIMITS`）：topics 20 / weak_points 8 / strengths 6 / summary 400 字符。
- 写入时机：finish 生命周期中的 `record_round_finished` 把摘要折叠进流程记忆并推进流程状态。

## 裁定与报告

| 步骤 | 位置 |
| --- | --- |
| 1 | 面试官 agent 在收尾轮宣布裁定（`passed` / `failed`） |
| 2 | 结束（WS 或 `POST .../finish`）→ `agents/finish_lifecycle.py: run_finish_lifecycle` 冻结会话台账、标记会话 completed、折叠轮次摘要、通知订阅方 |
| 3 | `notify_interview_finished` 钩子 → records 域 `services/ingest.py: handle_interview_finished`（幂等；已是 ready / generating 的报告跳过） |
| 4 | `services/debrief_runner.py: run_debrief_for_session` — CAS 抢占（`pending` / `failed` / 过期 `generating` → `generating`），运行报告 agent，持久化，通知报告摘要 |
| 5 | records 域 `agents/report/agent.py: DeepReportAgent` — 基于冻结台账的两阶段 ReAct 管线：阶段 1 轮次笔记（每批 12 轮，至多 2 批并行），阶段 2 汇总产出对齐的裁定、评分、亮点 / 关键问题与训练计划；总时长预算 480 秒 |
| 6 | 报告行状态 `pending` / `generating` / `ready` / `failed`（`services/report_store.py`）；`GET /api/v1/reports/{session_id}` 读取，`POST .../retry` 重跑，`GET .../stream` 伪流式输出 |
