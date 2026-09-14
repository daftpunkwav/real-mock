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

export const growthHttp = {
  getGrowthHistory: () => request<GrowthRecord[]>("/v1/growth/history"),
  getSystemInsights: () => request<SystemGrowthInsights>("/v1/growth/system-insights"),
  getAggregated: () => request<GrowthAggregatedStats>("/v1/growth/aggregated"),
};
