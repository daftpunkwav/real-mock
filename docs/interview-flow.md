# Multi-Round Interview Flow

The interview flow has two layers: a phase workflow inside one session, and an optional multi-round process that chains sessions into a realistic company loop.

## Phase / workflow SSOT

- Backend SSOT: `domains/interview/workflows.py` — `PhaseDef` (id / name / description / `min_questions` / `max_questions`); phase ids come from `InterviewPhaseId` in `domains/interview/constants.py`.
- Frontend mirror: `apps/web/src/config/phases.ts` — `PHASE_LABELS` (English label lock) and `PHASE_ORDER`; UI copy is localized via the `interview.phase.*` i18n namespace.
- Guard: `apps/api/tests/interview/test_phase_ssot.py` (workflow phase ids ↔ `InterviewPhaseId` ↔ frontend `PHASE_ORDER` / labels).

## Workflows

| Workflow id | Name | Phases in order (id, questions min–max) |
| --- | --- | --- |
| `technical` | Technical Interview | `identity_check` 1–1 → `self_intro` 1–1 → `basic_knowledge` 2–4 → `project_deep_dive` 3–6 → `technical_deep` 2–4 → `system_design` 1–2 → `scenario` 1–2 → `reverse_qa` 1–3 → `summary` 1–1 |
| `hr` | HR Interview | `identity_check` 1–1 → `self_intro` 1–1 → `career_plan` 2–3 → `teamwork` 2–3 → `pressure` 1–2 → `salary` 1–1 → `reverse_qa` 1–3 → `summary` 1–1 |
| `management` | Management Interview | `identity_check` 1–1 → `self_intro` 1–1 → `leadership` 2–4 → `decision_making` 2–3 → `conflict` 1–2 → `business` 2–3 → `reverse_qa` 1–3 → `summary` 1–1 |

Unknown workflow ids fall back to `technical` (`get_workflow`).

## Single session

A standalone session runs one workflow: `POST /api/v1/interview/sessions` → `POST .../start` → `POST .../message` turns → `POST .../finish` (HTTP turn API; the room itself runs over the WebSocket, see [realtime-protocol.md](interfaces/realtime-protocol.md)). A session starts at phase `identity_check`; phase switches are pushed as `phase_changed` events. On the wrap-up turn the interviewer agent announces the round verdict — `passed` / `failed` (`InterviewResult`) — carried on `assistant_done.result` and persisted on the session.

## Process (multi-round)

| Aspect | Behavior |
| --- | --- |
| Creation | `POST /api/v1/interview/processes` creates the process and its round-1 session in one transaction (`process/process_service.py: create_process_with_first_round`) |
| Round budget | `max_rounds`: 1–`MAX_INTERVIEW_ROUNDS` (5), default 5 (`schemas/process.py`) |
| Next round | `POST /api/v1/interview/processes/{process_id}/rounds`; eligibility (`is_next_round_eligible`): process `in_progress`, latest round `completed` and `passed`, budget remaining |
| Status | `ProcessStatus`: `in_progress` / `completed` / `abandoned`; a failed round, or reaching the cap with a pass, completes the process (`record_round_finished`) |

## Round planning

Two sources; the HR-planned program rules when ready, otherwise the static chain decides (`_session_from_process`):

- Static chains — `protocols/round_chain.py`: one canonical chain per base workflow; each `RoundStep` fixes the round's `workflow_type` / `personality` / `interview_style` / `strictness` / `focus` / `label`. Round kinds (pinned vocabulary, frontend i18n keys): `tech_1`, `tech_2`, `tech_deep`, `hr_1`, `hr_2`, `mgmt`, `cross`.
- HR planner program — `protocols/round_plan_schema.py` (schema `realmock.round_plan.v1`): the planner agent authors rounds including `pass_criteria`; parsing is tolerant per field, structural garbage falls back to the static chain.

Canonical chains (`round_chain()`); a process uses the first `max_rounds` (≤ 5) steps and the last used step always carries the final overall judgement:

| Round | `technical` base | `hr` base | `management` base |
| --- | --- | --- | --- |
| 1 | Technical Round 1 (`tech_1`) | HR Round 1 (`hr_1`) | Management Round 1 (`mgmt`) |
| 2 | Technical Round 2 (`tech_2`) | HR Round 2 (`hr_2`) | Management Round 2 (`mgmt`) |
| 3 | HR Round 1 (`hr_1`) | Technical Round 1 (`tech_1`) | HR Round 1 (`hr_1`) |
| 4 | HR Round 2 (`hr_2`) | Technical Round 2 (`tech_2`) | HR Round 2 (`hr_2`) |
| 5 | Technical Cross-check (`tech_deep`) | Management Round (`mgmt`) | Technical Round (`tech_1`) |
| 6 | Final Loop (`cross`) | HR Round 3 (`hr_2`) | Executive Round (`cross`) |
| 7 | Stress Round (`tech_deep`) | Final Loop (`cross`) | HR Judgement (`hr_2`) |
| 8 | Executive Round (`cross`) | Stress Round (`tech_deep`) | Stress Round (`tech_deep`) |

Each step also carries persona overrides; for example the `technical` chain runs round 1 as `expert` / `deep_dive` / strictness 3 and round 2 as `expert` / `challenging` / strictness 5.

## Process memory (per-round digest)

- Document: `realmock.process_memory.v1` (`protocols/process_memory.py`) — `{schema, rounds[], final}`, stored on `interview_processes.memory` and consumed by the planner and interviewer prompts as cross-round memory.
- Digest: `process/round_digest.py: build_round_digest` — rule-based, no LLM calls; built from the interviewer agent's structured state (asked questions, weak points, last turn score) plus frozen-ledger phase coverage. Limits (`DIGEST_LIMITS`): 20 topics / 8 weak points / 6 strengths / 400 summary chars.
- Write time: `record_round_finished` in the finish lifecycle folds the digest into process memory and advances process status.

## Verdict and report

| Step | Where |
| --- | --- |
| 1 | The interviewer agent announces the verdict (`passed` / `failed`) on the wrap-up turn |
| 2 | Finish (WS or `POST .../finish`) → `agents/finish_lifecycle.py: run_finish_lifecycle` freezes the session ledger, marks the session completed, folds the round digest, notifies subscribers |
| 3 | `notify_interview_finished` hook → records domain `services/ingest.py: handle_interview_finished` (idempotent; skips reports already ready / generating) |
| 4 | `services/debrief_runner.py: run_debrief_for_session` — CAS claim (`pending` / `failed` / stale `generating` → `generating`), runs the report agent, persists, notifies the report summary |
| 5 | `agents/report/agent.py: DeepReportAgent` — two-stage ReAct pipeline over the frozen ledger: stage 1 turn notes (12 turns per batch, up to 2 batches in parallel), stage 2 synthesis producing the aligned verdict, scores, highlights / key problems and the training plan; wall-clock budget 480 s |
| 6 | Report row statuses `pending` / `generating` / `ready` / `failed` (`services/report_store.py`); read via `GET /api/v1/reports/{session_id}`, re-run via `POST .../retry`, pseudo-stream via `GET .../stream` |
