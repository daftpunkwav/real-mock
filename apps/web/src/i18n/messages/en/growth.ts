/** growth messages (filled in as the feature migrates; keys must mirror zh-CN). */

export const growth = {
  // Page level (app/growth/page.tsx + useGrowthPage load-failure fallback)
  "page.eyebrow": "Growth",
  "page.title": "Growth Tracking",
  "page.loading": "Loading…",
  "page.loadFailed": "Failed to load",

  // AI growth insight (InsightCard)
  "insight.title": "AI Growth Insights",
  "insight.refresh": "Regenerate",
  "insight.generate": "Generate growth analysis",
  "insight.generating": "AI is analyzing your interview history…",
  "insight.loading": "Loading…",
  "insight.empty": "After an interview, AI builds a cross-session growth analysis from all reports, your resume, and profile.",
  "insight.stage.rising": "Rising",
  "insight.stage.stalling": "Stalling",
  "insight.stage.plateau": "Plateau",
  "insight.stage.insufficient": "Insufficient data",
  "insight.patterns": "Recurring weaknesses",
  "insight.appearedIn": "{count} sessions",
  "insight.trend.worsening": "worsening",
  "insight.trend.stable": "stable",
  "insight.trend.improving": "improving",
  "insight.improving": "Measurable progress",
  "insight.gaps": "Resume vs interview gaps",
  "insight.plan": "Next-stage training plan",
  "insight.basedOn": "Based on the latest {count} interview reports",

  // Growth summary card (GrowthSummaryCard + local level labels)
  "summary.level.none": "Not started",
  "summary.level.starting": "Getting started",
  "summary.level.growing": "Steady growth",
  "summary.level.advanced": "Advancing",
  "summary.recordsIntro": "Accumulated {count} growth records",
  "summary.empty": "Awaiting your first interview",
  "summary.recordsLabel": "Interviews",
  "summary.plansLabel": "Plans",
  "summary.weakSkillsLabel": "Weak skills",
  "summary.lastTraining": "Last session",
  "summary.records": "{count} sessions",
  "summary.plans": "{count} items",
  "summary.weakSkills": "{count} skills",
  "summary.focusTitle": "Focus areas",
  "summary.planTitle": "Current plan",

  // Growth progress card (GrowthProgressCard)
  "progress.title": "Growth completion",
  "progress.hint": "Complete more interviews and follow training plans to raise completion.",
  "progress.interviewCta": "Mock interview",
  "progress.prepCta": "Interview prep",

  // Training history (TrainingHistorySection)
  "history.title": "Training history",
  "history.session": "Interview #{id}",
  "history.report": "Report →",
  "history.empty": "Growth records are generated after interviews",
  "history.startCta": "Start mock interview",

  // Top weaknesses (TopWeaknessesSection)
  "weaknesses.title": "Top weaknesses",
  "weaknesses.occurrences": "Seen {count} times",
  "weaknesses.empty": "Weak skills are aggregated automatically after mock interviews",

  // System self-growth (SystemInsightsSection)
  "insights.title": "System self-growth",
  "insights.description": "Cross-interview aggregation: company distribution, tool usage, accumulated weak points.",
  "insights.toolsOn": " Tool loop is enabled.",
  "insights.toolsOff": " Tool loop is disabled.",
  "insights.githubConfigured": " GitHub Token is configured.",
  "insights.githubMissing": " GITHUB_TOKEN is not configured.",
  "insights.sessionCount": "{count} sessions",
  "insights.recentProbes": "Recent probes",
  "insights.probeItem": "· [{company}] {point}",
} as const;

export type GrowthMessageKey = keyof typeof growth;
