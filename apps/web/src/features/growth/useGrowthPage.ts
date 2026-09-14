"use client";

/**
 * Growth page data domain: history + insights + aggregated stats.
 * Prefers `/growth/aggregated` from GrowthAgent; falls back to local computeGrowthStats.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { growthHttp as api } from "@/lib/api/clients";
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

/** Growth page load domain: history + insights + aggregated stats + LoadError retry. */
export function useGrowthPage() {
  const [records, setRecords] = useState<GrowthRecord[]>([]);
  const [insights, setInsights] = useState<SystemInsights | null>(null);
  const [aggregated, setAggregated] = useState<GrowthStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const seqRef = useRef(0);

  const load = useCallback(async () => {
    const seq = ++seqRef.current;
    setLoading(true);
    setLoadError(null);
    try {
      const [list, sys, agg] = await Promise.all([
        api.getGrowthHistory(),
        api.getSystemInsights().catch(() => null),
        api.getAggregated().catch(() => null),
      ]);
      if (seq !== seqRef.current) return;
      setRecords(list);
      setInsights(sys);
      setAggregated(agg ? mapAggregated(agg as Record<string, unknown>) : null);
      setSelectedId(list[0]?.id ?? null);
    } catch (e) {
      if (seq !== seqRef.current) return;
      setLoadError(
        e instanceof Error ? e.message : getTranslator("growth")("page.loadFailed"),
      );
    } finally {
      if (seq !== seqRef.current) return;
      setLoading(false);
    }
  }, []);

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
  };
}
