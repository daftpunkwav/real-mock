/** Growth tracking REST client. */

import type { GrowthRecord } from "@/types";
import { request } from "@/lib/api/base";

/** Growth-domain system-insights (not modeled in OpenAPI) */
export type SystemGrowthInsights = {
  company_session_counts: Record<string, number>;
  role_session_counts: Record<string, number>;
  avg_scores_by_company: Record<string, number | null>;
  followup_category_hits: Record<string, number>;
  tool_call_counts: Record<string, number>;
  recent_probes: {
    company?: string;
    role?: string;
    point?: string;
    session_id?: number;
  }[];
  updated_at?: string | null;
  github_token_configured?: boolean;
  interview_tools_enabled?: boolean;
};

/** Precomputed growth page stats from GrowthAgent (rule-based). */
export type GrowthAggregatedStats = {
  top_weaknesses: [string, number][];
  total_interviews: number;
  total_plans: number;
  total_weak_skills: number;
  growth_pct: number;
  growth_level: string;
};


/** LLM growth insight payload (GET /growth/insight; hand-written contract). */
export type GrowthWeaknessPattern = {
  skill: string;
  count: number;
  trend: string;
  advice: string;
};

export type GrowthTrainingFocus = {
  area: string;
  based_on: string;
  actions: string[];
};

export type GrowthInsight = {
  headline: string;
  trajectory: string;
  trajectory_stage: "rising" | "stalling" | "plateau" | "insufficient";
  recurring_weaknesses: GrowthWeaknessPattern[];
  improving_areas: string[];
  resume_gap_insights: string[];
  training_plan: GrowthTrainingFocus[];
  generated_at: string | null;
  session_count: number;
  locale: string;
};

export type GrowthInsightEnvelope = {
  insight: GrowthInsight | null;
  status?: "ready" | "generating" | "empty";
};

export const growthHttp = {
  getGrowthHistory: () => request<GrowthRecord[]>("/v1/growth/history"),
  getSystemInsights: () => request<SystemGrowthInsights>("/v1/growth/system-insights"),
  getAggregated: () => request<GrowthAggregatedStats>("/v1/growth/aggregated"),
  getInsight: () => request<GrowthInsightEnvelope>("/v1/growth/insight"),
  refreshInsight: (locale?: string) =>
    request<{ scheduled: boolean; status: string }>(
      `/v1/growth/insight/refresh${locale ? `?locale=${encodeURIComponent(locale)}` : ""}`,
      { method: "POST" },
    ),
};
