"use client";

/**
 * Growth page data domain: history + insights + aggregated stats.
 * Prefers `/growth/aggregated` from GrowthAgent; falls back to local computeGrowthStats.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { growthHttp as api } from "@/lib/api/clients";
import type { GrowthInsight } from "@/lib/api/clients";
import { getTranslator } from "@/i18n/resolve";
import type { GrowthRecord } from "@/types";
import { computeGrowthStats } from "./growthStats";
import type { SystemInsights } from "./types";

type GrowthStats = ReturnType<typeof computeGrowthStats>;

function mapAggregated(raw: Record<string, unknown>): GrowthStats | null {
  try {
    const top = raw.top_weaknesses;
    if (!Array.isArray(top)) return null;
    return {
      topWeaknesses: top as [string, number][],
      totalInterviews: Number(raw.total_interviews ?? 0),
      totalPlans: Number(raw.total_plans ?? 0),
      totalWeakSkills: Number(raw.total_weak_skills ?? 0),
      growthPct: Number(raw.growth_pct ?? 0),
      // Backend-provided level name passes through; only the missing-field
      // fallback uses the local "not started" label from the catalog.
      growthLevel: String(raw.growth_level ?? getTranslator("growth")("summary.level.none")),
    };
  } catch {
    return null;
  }
}

const INSIGHT_POLL_INTERVAL_MS = 3000;
const INSIGHT_POLL_MAX = 60;

type InsightEnvelope = Awaited<ReturnType<typeof api.getInsight>>;

/**
 * Guarantee the array fields exist so the card never crashes on a degraded
 * backend payload: the store falls back to an empty object when the stored
 * insight JSON is corrupted, which yields an insight with no arrays at all.
 */
export function normalizeInsight(raw: GrowthInsight): GrowthInsight {
  return {
    ...raw,
    recurring_weaknesses: Array.isArray(raw.recurring_weaknesses) ? raw.recurring_weaknesses : [],
    improving_areas: Array.isArray(raw.improving_areas) ? raw.improving_areas : [],
    resume_gap_insights: Array.isArray(raw.resume_gap_insights) ? raw.resume_gap_insights : [],
    training_plan: Array.isArray(raw.training_plan)
      ? raw.training_plan.map((focus) => ({
          ...focus,
          actions: Array.isArray(focus.actions) ? focus.actions : [],
        }))
      : [],
  };
}

/** Growth page load domain: history + insights + aggregated stats + LoadError retry. */
export function useGrowthPage() {
  const [records, setRecords] = useState<GrowthRecord[]>([]);
  const [insights, setInsights] = useState<SystemInsights | null>(null);
  const [aggregated, setAggregated] = useState<GrowthStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [aiInsight, setAiInsight] = useState<InsightEnvelope["insight"]>(null);
  const [aiStatus, setAiStatus] = useState<"loading" | "empty" | "generating" | "ready">("loading");
  const seqRef = useRef(0);

  const applyInsight = useCallback((env: InsightEnvelope | null) => {
    if (!env) {
      setAiStatus("empty");
      return;
    }
    setAiInsight(env.insight ? normalizeInsight(env.insight) : null);
    // A regen in flight wins over the stale snapshot: staying "generating"
    // keeps the poller alive so the fresh analysis actually surfaces when it
    // lands (an existing insight must not short-circuit that).
    setAiStatus(env.status === "generating" ? "generating" : env.insight ? "ready" : "empty");
  }, []);

  // While the backend reports a regen in flight, poll until it settles.
  useEffect(() => {
    if (aiStatus !== "generating") return;
    let tries = 0;
    const id = window.setInterval(async () => {
      tries += 1;
      if (tries > INSIGHT_POLL_MAX) {
        window.clearInterval(id);
        setAiStatus("ready");
        return;
      }
      try {
        const env = await api.getInsight();
        // Keep polling while the backend is still regenerating, even when a
        // previous insight is present; applying it now would stop the poll
        // and the regenerated analysis would never reach the page.
        if (env.status === "generating") return;
        window.clearInterval(id);
        applyInsight(env);
      } catch {
        /* transient network errors: keep polling until the cap */
      }
    }, INSIGHT_POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [aiStatus, applyInsight]);

  const refreshInsight = useCallback(async (locale?: string) => {
    try {
      await api.refreshInsight(locale);
      setAiStatus("generating");
    } catch {
      /* refresh failures surface on the next manual attempt */
    }
  }, []);

  const load = useCallback(async () => {
    const seq = ++seqRef.current;
    setLoading(true);
    setLoadError(null);
    try {
      const [list, sys, agg, insightEnv] = await Promise.all([
        api.getGrowthHistory(),
        api.getSystemInsights().catch(() => null),
        api.getAggregated().catch(() => null),
        api.getInsight().catch(() => null),
      ]);
      if (seq !== seqRef.current) return;
      setRecords(list);
      setInsights(sys);
      setAggregated(agg ? mapAggregated(agg as Record<string, unknown>) : null);
      setSelectedId(list[0]?.id ?? null);
      applyInsight(insightEnv);
    } catch (e) {
      if (seq !== seqRef.current) return;
      setLoadError(
        e instanceof Error ? e.message : getTranslator("growth")("page.loadFailed"),
      );
    } finally {
      if (seq !== seqRef.current) return;
      setLoading(false);
    }
  }, [applyInsight]);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = useMemo(
    () => records.find((r) => r.id === selectedId) ?? null,
    [records, selectedId],
  );

  const localStats = useMemo(() => computeGrowthStats(records), [records]);
  const stats = aggregated ?? localStats;

  return {
    records,
    insights,
    loading,
    loadError,
    selectedId,
    setSelectedId,
    selected,
    stats,
    load,
    aiInsight,
    aiStatus,
    refreshInsight,
  };
}
