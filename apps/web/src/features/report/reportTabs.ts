/** Deep report tab structure (SSOT): ids, i18n label keys, content-derived visibility. */

import type { MessageKey } from "@/i18n";
import type { DebriefReport } from "@/types/domains/report";

export type ReportTabId = "overview" | "turns" | "verdict" | "plan";

export const REPORT_TAB_IDS: ReportTabId[] = ["overview", "turns", "verdict", "plan"];

export const REPORT_TAB_LABEL_KEYS: Record<ReportTabId, MessageKey<"report">> = {
  overview: "tabs.overview",
  turns: "tabs.turns",
  verdict: "tabs.verdict",
  plan: "tabs.plan",
};

/** Tabs that have content for this report; overview is always present. */
export function visibleReportTabIds(report: DebriefReport): ReportTabId[] {
  const tabs: ReportTabId[] = ["overview"];
  if ((report.turn_notes ?? []).length > 0) tabs.push("turns");
  if (
    report.verdict ||
    (report.highlights ?? []).length > 0 ||
    (report.key_problems ?? []).length > 0
  ) {
    tabs.push("verdict");
  }
  if ((report.training_plan ?? []).length > 0) tabs.push("plan");
  return tabs;
}

/** First tab that actually has content (tab bar ignores empty ones). */
export function defaultReportTab(report: DebriefReport): ReportTabId {
  return visibleReportTabIds(report)[0] ?? "overview";
}
