/**
 * @file analysisTabs
 * @description Which analysis sheet tabs have content (no React).
 *
 * Responsibilities:
 * - Derive visible TabId list from a ResumeAnalysis payload
 * - Own tab id / i18n key maps so AnalysisPanel stays layout-only
 *
 * Icons stay in AnalysisPanel. Must not import React.
 */

import type { MessageKey } from "@/i18n";
import type { ResumeAnalysis } from "@/lib/api/contract";

export type TabId =
  | "overview"
  | "document"
  | "projects"
  | "interview"
  | "advice"
  | "career";

export const ANALYSIS_TAB_IDS: readonly TabId[] = [
  "overview",
  "document",
  "projects",
  "interview",
  "advice",
  "career",
] as const;

export const TAB_LABEL_KEYS: Record<TabId, MessageKey<"resume">> = {
  overview: "analysis.tab.overview",
  document: "analysis.tab.document",
  projects: "analysis.tab.projects",
  interview: "analysis.tab.interview",
  advice: "analysis.tab.advice",
  career: "analysis.tab.career",
};

export function visibleAnalysisTabIds(analysis: ResumeAnalysis): TabId[] {
  const tabs: TabId[] = ["overview"];
  const hasDocument =
    !!analysis.layout_review ||
    !!analysis.typography_review ||
    !!analysis.content_review ||
    (analysis.section_reviews?.length ?? 0) > 0;
  const hasProjects =
    (analysis.project_cards?.length ?? 0) > 0 ||
    (analysis.project_deep_dive?.length ?? 0) > 0 ||
    (analysis.repo_verification?.length ?? 0) > 0 ||
    (analysis.repo_evidence?.length ?? 0) > 0;
  const hasInterview =
    (analysis.interview_qa?.length ?? 0) > 0 ||
    (analysis.predicted_questions?.length ?? 0) > 0 ||
    (analysis.interview_risk_areas?.length ?? 0) > 0;
  const hasAdvice =
    (analysis.red_flags?.length ?? 0) > 0 ||
    (analysis.improvement_suggestions?.length ?? 0) > 0 ||
    (analysis.rewrite_examples?.length ?? 0) > 0 ||
    (analysis.ats_keywords?.length ?? 0) > 0 ||
    (analysis.missing_keywords?.length ?? 0) > 0 ||
    (analysis.strengths?.length ?? 0) > 0 ||
    (analysis.weaknesses?.length ?? 0) > 0 ||
    analysis.skill_trust != null;
  const hasCareer =
    analysis.career_analysis != null ||
    !!analysis.salary_positioning ||
    (analysis.company_fit?.length ?? 0) > 0 ||
    (analysis.market_insights?.length ?? 0) > 0;
  if (hasDocument) tabs.push("document");
  if (hasProjects) tabs.push("projects");
  if (hasInterview) tabs.push("interview");
  if (hasAdvice) tabs.push("advice");
  if (hasCareer) tabs.push("career");
  return tabs;
}
