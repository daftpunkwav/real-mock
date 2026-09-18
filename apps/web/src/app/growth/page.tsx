"use client";

/** Growth-tracking page: aggregated insights and weak-point skills. */

import { TrendingUp } from "lucide-react";
import { LoadError } from "@/components/LoadError";
import { useT } from "@/i18n";
import { useGrowthPage } from "@/features/growth/useGrowthPage";
import { TopWeaknessesSection } from "@/features/growth/components/TopWeaknessesSection";
import { SystemInsightsSection } from "@/features/growth/components/SystemInsightsSection";
import { TrainingHistorySection } from "@/features/growth/components/TrainingHistorySection";
import { GrowthSummaryCard } from "@/features/growth/components/GrowthSummaryCard";
import { GrowthProgressCard } from "@/features/growth/components/GrowthProgressCard";

export default function GrowthPage() {
  const t = useT("growth");
  const { records, insights, loading, loadError, selectedId, setSelectedId, selected, stats, load } =
    useGrowthPage();

  return (
    <div className="page-shell anim-rise">
      <div className="page-header">
        <div className="flex items-start gap-3">
          <span className="icon-badge icon-badge-brand">
            <TrendingUp size={18} strokeWidth={1.75} />
          </span>
          <div>
            <p className="page-eyebrow">{t("page.eyebrow")}</p>
            <h1 className="page-title">{t("page.title")}</h1>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-[13px] text-ink-muted">
          <span className="block h-4 w-4 anim-spin rounded-full border-2 border-current border-t-transparent" />
          {t("page.loading")}
        </div>
      ) : loadError ? (
        <LoadError message={loadError} onRetry={load} />
      ) : (
        <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
          <div className="min-w-0 space-y-4">
            <TopWeaknessesSection
              topWeaknesses={stats.topWeaknesses}
              totalInterviews={stats.totalInterviews}
            />
            {insights && <SystemInsightsSection insights={insights} />}
            <TrainingHistorySection
              records={records}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          </div>
          <aside className="space-y-3 xl:sticky xl:top-6">
            <GrowthSummaryCard
              growthLevel={stats.growthLevel}
              totalInterviews={stats.totalInterviews}
              totalPlans={stats.totalPlans}
              totalWeakSkills={stats.totalWeakSkills}
              selected={selected}
              topWeaknesses={stats.topWeaknesses}
            />
            <GrowthProgressCard growthPct={stats.growthPct} />
          </aside>
        </div>
      )}
    </div>
  );
}
