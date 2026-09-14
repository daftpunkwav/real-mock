import type { ReactNode } from "react";
import { ArrowRight, ExternalLink, FileText, Play, TrendingUp } from "lucide-react";
import Link from "next/link";
import type { SessionHistoryItem } from "@/types/domains/records";
import { formatDateTime, useT } from "@/i18n";
import { ResultBadge, RoundBadge } from "./ResultBadge";
import { StatusBadge } from "./StatusBadge";
import { StatCell } from "./StatCell";

/** Detail row: label + value. */
function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="shrink-0 pt-0.5 text-[10px] uppercase tracking-[0.08em] text-ink-subtle">
        {label}
      </span>
      <span className="text-right text-[13px] font-medium text-ink">{value}</span>
    </div>
  );
}

/** Aside: stats overview + selected session detail and actions. */
export function HistoryDetailAside({
  selected,
  stats,
  nextRoundNo,
  startingNext,
  onStartNextRound,
}: {
  selected: SessionHistoryItem | null;
  stats: { total: number; completed: number; active: number; avgScore: number | null };
  nextRoundNo?: number | null;
  startingNext?: boolean;
  onStartNextRound?: () => void;
}) {
  const t = useT("history");
  const when = selected?.created_at ?? selected?.started_at;

  return (
    <aside className="space-y-3 xl:sticky xl:top-6">
      <div className="surface-card p-5">
        <h2 className="mb-3.5 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
          <TrendingUp size={14} className="text-[var(--primary)]" />
          {t("stats.title")}
        </h2>
        <div className="grid grid-cols-2 gap-2">
          <StatCell value={stats.total} label={t("stats.total")} />
          <StatCell value={stats.completed} label={t("stats.completed")} tone="success" />
          <StatCell value={stats.active} label={t("stats.active")} tone="info" />
          <StatCell value={stats.avgScore ?? "—"} label={t("stats.avgScore")} />
        </div>
      </div>

      <div className="surface-card p-5">
        {selected ? (
          <>
            <h2 className="mb-3.5 text-[13px] font-semibold tracking-tight text-ink">
              {t("detail.title")}
            </h2>
            <dl className="space-y-2.5 text-sm">
              <DetailRow label={t("detail.role")} value={`${selected.role} · ${selected.level}`} />
              <DetailRow label={t("detail.company")} value={selected.company} />
              <DetailRow label={t("detail.type")} value={selected.workflow_type} />
              <DetailRow label={t("detail.status")} value={<StatusBadge status={selected.status} />} />
              {(selected.round_no || selected.result) && (
                <DetailRow
                  label={t("detail.roundResult")}
                  value={
                    <span className="flex items-center gap-1.5">
                      <RoundBadge roundNo={selected.round_no} />
                      <ResultBadge result={selected.result} />
                    </span>
                  }
                />
              )}
              {selected.ledger_frozen != null && (
                <DetailRow
                  label={t("detail.ledger")}
                  value={selected.ledger_frozen ? t("detail.ledgerFrozen") : t("detail.ledgerUnfrozen")}
                />
              )}
              {when && (
                <DetailRow label={t("detail.time")} value={formatDateTime(when)} />
              )}
              {selected.overall_score != null && (
                <DetailRow
                  label={t("detail.overallScore")}
                  value={
                    <span className="font-mono text-[16px] font-semibold text-[var(--primary)] num-tabular">
                      {selected.overall_score}
                    </span>
                  }
                />
              )}
              {selected.current_phase && selected.status === "active" && (
                <DetailRow label={t("detail.currentPhase")} value={selected.current_phase} />
              )}
            </dl>

            <div className="mt-5 space-y-2 border-t border-surface-border pt-4">
              {selected.status === "completed" ? (
                <Link href={`/report/${selected.id}`} className="btn-primary w-full">
                  <FileText size={13} />
                  {t("detail.viewReport")}
                  <ExternalLink size={13} />
                </Link>
              ) : selected.status === "active" ? (
                <Link href={`/interview/${selected.id}`} className="btn-primary w-full">
                  <Play size={13} />
                  {t("detail.continueInterview")}
                </Link>
              ) : (
                <p className="py-1 text-center text-[11px] text-ink-subtle">{t("detail.notStarted")}</p>
              )}
              {selected.status === "completed" && nextRoundNo && onStartNextRound && (
                <button
                  type="button"
                  className="btn-secondary w-full"
                  onClick={onStartNextRound}
                  disabled={startingNext}
                >
                  {startingNext ? (
                    <span className="block h-3.5 w-3.5 anim-spin rounded-full border-2 border-current border-t-transparent" />
                  ) : (
                    <ArrowRight size={13} />
                  )}
                  {t("detail.nextRound", { n: nextRoundNo })}
                </button>
              )}
            </div>
          </>
        ) : (
          <p className="py-6 text-center text-[13px] text-ink-subtle">{t("detail.empty")}</p>
        )}
      </div>
    </aside>
  );
}
