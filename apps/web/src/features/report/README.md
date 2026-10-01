# features/report/

Report page domain: load orchestration, tab structure, and per-turn analysis.

| Module | Purpose |
| --- | --- |
| `useReportLoad.ts` | Load state machine: fast-path GET, live SSE while generating, poll fallback, A2003 finish-commit retry, ledger fallback via recordsHttp; `retryGenerate` restarts the whole chain |
| `reportTabs.ts` | Tab SSOT: ids, i18n label keys, content-derived visibility (empty tabs never render); default tab is the first visible one |
| `turnGroups.ts` | Pure grouping of turn notes: ledger turn order inside a group, phase SSOT order across groups (unknown phases by first appearance, phase-less notes last) |
| `liveEvents.ts` | Reducer for live generation progress events (keeps the last 40) |
| `scoreFormat.ts` | Score rounding; missing values render as an em dash |
| `components/` | One card per report section; `TurnDeepNotes` paginates per-turn notes by phase (inactive groups stay mounted, hidden, to keep fold state) |

`app/report/[id]/page.tsx` is the only page consumer: it owns tab selection
and renders only the active panel.
