/** report messages (interview report domain; keys must mirror zh-CN). */

export const report = {
  // Page level (app/report/[id]/page.tsx + useReportLoad failure fallbacks)
  "page.loading": "Generating report…",
  "page.retryCta": "Generate / Reload",
  "page.backToInterview": "Back to Interview",
  "errors.unavailable": "Report unavailable",
  "errors.invalidSession": "Invalid session ID",
  "errors.generateFailed": "Report generation failed, please retry",
  "errors.notGenerated":
    "Report not generated yet. Click the button below to generate or reload.",

  // Score summary card (ScoreSummaryCard)
  "summary.backLink": "Back to History",
  "summary.eyebrow": "Report",
  "summary.title": "Interview Assessment Report",
  "summary.duration": "Duration: {duration} min",
  "summary.messagesCount": " · {count} effective messages",
  "summary.overallScore": "Overall Score / 100",

  // Short session alert (ShortSessionAlert)
  "alerts.shortSession":
    "This session was short or had few effective responses, so dimension scores may be low or near 0. This reflects the assessment itself, not missing data.",

  // Dimension scores (DimensionScores)
  "dimensions.technical": "Technical",
  "dimensions.communication": "Communication",
  "dimensions.projectDepth": "Project Depth",
  "dimensions.problemSolving": "Problem Solving",
  "dimensions.presence": "Presence",
  "dimensions.politeness": "Politeness",

  // Ability radar (ScoreRadar)
  "radar.title": "Ability Radar",
  "radar.subtitle": "Each axis is out of 100; a score of 0 sits near the center",
  "radar.technical": "Tech",
  "radar.communication": "Comm",
  "radar.projectDepth": "Project",
  "radar.problemSolving": "Solving",
  "radar.presence": "Presence",
  "radar.politeness": "Politeness",
  "radar.empty": "No valid dimension scores",

  // Section titles (app/report/[id]/page.tsx → Section)
  "sections.strengths": "Strengths",
  "sections.weaknesses": "Weaknesses",
  "sections.resumeSuggestions": "Resume Suggestions",
  "sections.interviewSuggestions": "Interview Suggestions",
  "sections.improvementSuggestions": "Overall Suggestions",
  "sections.trainingPlan": "Next-Stage Training Plan",
  "sections.presenceMoments": "Key Presence Moments",

  // Face analysis card (FaceAnalysisCard)
  "face.title": "Interview State Analysis",

  // Footer actions (ActionLinks)
  "actions.again": "Go Again",
  "actions.growth": "View Growth Records",

  // Session replay (SessionLedgerReplay)
  "turns.replayTitle": "Session Replay",
  "turns.ledgerFrozen": "ledger frozen",
  "turns.count": "{count} turns",
  "turns.interviewer": "Interviewer",
  "turns.tools": "Tools",
  "turns.candidate": "Candidate",
  "turns.expand": "Expand",
  "turns.collapse": "Collapse",
  "turns.toolOk": "ok",
  "turns.toolFail": "fail",
  "turns.toolArgs": "args",
  "turns.toolResult": "result",
  "turns.toolNameFallback": "tool",

  // Turn notes (TurnNotesSection)
  "turns.notesTitle": "Turn-by-Turn Notes",
  "turns.candidatePerformance": "Candidate Performance",
  "turns.interviewerReview": "Interviewer Review",
  "turns.intentLabel": "Intent:",
  // Deep report (ReAct report agent)
  "tabs.overview": "Overview",
  "tabs.turns": "Q&A Deep Dive",
  "tabs.verdict": "Highlights & Problems",
  "tabs.plan": "Improvement Plan",
  "verdict.passed": "Verdict: Passed",
  "verdict.failed": "Verdict: Failed",
  "sections.highlights": "Highlights",
  "sections.keyProblems": "Key Problems",
  "qa.intent": "Question intent",
  "qa.problems": "What went wrong",
  "qa.reference": "Reference answer",
  "qa.howToAnswer": "How to answer",
  "qa.brushup": "Knowledge brush-up",
  "qa.exercises": "Practice drills",
  "qa.followup": "Follow-up handling",
  "live.title": "Generating your report",
  "live.starting": "Starting the report agent…",
  "live.stageNotes": "Reading the transcript and resume evidence per question",
  "live.stageSynthesis": "Synthesizing scores and the final verdict",
  "live.tool": "Verifying: {name}",
  "live.thinking": "Thinking…",
  "live.working": "Searching…",
    "turns.qualityLabel": "Quality:",
} as const;

export type ReportMessageKey = keyof typeof report;
