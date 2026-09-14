"use client";

/** Mock-interview history page: session list with report access. */

import { BarChart3 } from "lucide-react";
import { LoadError } from "@/components/LoadError";
import { useT } from "@/i18n";
import { useHistoryPage } from "@/features/history/useHistoryPage";
import { HistoryListCard } from "@/features/history/components/HistoryListCard";
import { HistoryDetailAside } from "@/features/history/components/HistoryDetailAside";

export default function HistoryPage() {
  const t = useT("history");
  const {
    sessions,
    loading,
    loadError,
    selectedId,
    setSelectedId,
    selected,
    stats,
    nextRoundIndex,
    startingNext,
    startNextRound,
    load,
  } = useHistoryPage();
  const selectedProcessId = selected?.process_id ?? null;
  const nextRoundNo = selectedProcessId
    ? nextRoundIndex[selectedProcessId]?.next_round_no ?? null
    : null;

  return (
    <div className="page-shell anim-rise">
      <div className="page-header">
        <div className="flex items-start gap-3">
          <span className="icon-badge icon-badge-brand">
            <BarChart3 size={18} strokeWidth={1.75} />
          </span>
          <div>
            <p className="page-eyebrow">{t("list.eyebrow")}</p>
            <h1 className="page-title">{t("list.title")}</h1>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-[13px] text-ink-muted">
          <span className="block h-4 w-4 anim-spin rounded-full border-2 border-current border-t-transparent" />
          {t("list.loading")}
        </div>
      ) : loadError ? (
        <LoadError message={loadError} onRetry={load} />
      ) : (
        <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
          <HistoryListCard
            sessions={sessions}
            selectedId={selectedId}
            onSelect={setSelectedId}
            total={stats.total}
          />
          <HistoryDetailAside
            selected={selected}
            stats={stats}
            nextRoundNo={nextRoundNo}
            startingNext={startingNext}
            onStartNextRound={
              selectedProcessId ? () => startNextRound(selectedProcessId) : undefined
            }
          />
        </div>
      )}
    </div>
  );
}
