/** history messages (interview history domain; keys must mirror zh-CN). */

export const history = {
  // Page header + list (app/history/page.tsx + useHistoryPage + HistoryListCard)
  "list.eyebrow": "History",
  "list.title": "Interview History",
  "list.loading": "Loading records…",
  "list.loadFailed": "Failed to load",
  "list.allSessions": "All Sessions",
  "list.total": "{count} sessions",
  "list.empty": "No interview records yet",
  "list.startCta": "Start Mock Interview",
  "list.ledgerBadge": "ledger",

  // Session status badge (StatusBadge)
  "status.completed": "Completed",
  "status.active": "In Progress",
  "status.pending": "Not Started",

  // Stats overview cells (HistoryDetailAside + StatCell)
  "stats.title": "Overview",
  "stats.total": "Total Sessions",
  "stats.completed": "Completed",
  "stats.active": "In Progress",
  "stats.avgScore": "Avg Score",

  // Session detail (HistoryDetailAside)
  "detail.title": "Session Details",
  "detail.role": "Role",
  "detail.company": "Company",
  "detail.type": "Type",
  "detail.status": "Status",
  "detail.ledger": "Ledger",
  "detail.ledgerFrozen": "Frozen",
  "detail.ledgerUnfrozen": "Not Frozen",
  "detail.time": "Time",
  "detail.overallScore": "Overall Score",
  "detail.currentPhase": "Current Phase",
  "detail.viewReport": "View Report",
  "detail.continueInterview": "Resume Interview",
  "detail.notStarted": "This session has not started yet",
  // Multi-round interviews (round 1..5)
  "list.round": "Round {n}",
  "result.passed": "Passed",
  "result.failed": "Failed",
  "detail.roundResult": "Round result",
  "detail.nextRound": "Start round {n}",
  "detail.nextRoundFailed": "Failed to start the next round",

  "detail.empty": "Select a record to see details",
} as const;

export type HistoryMessageKey = keyof typeof history;
