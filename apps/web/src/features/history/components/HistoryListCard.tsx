import { BarChart3, Play } from "lucide-react";
import Link from "next/link";
import type { SessionHistoryItem } from "@/types/domains/records";
import { formatDateTime, useT } from "@/i18n";
import { ResultBadge, RoundBadge } from "./ResultBadge";
import { StatusBadge } from "./StatusBadge";

/** History list: title + total chip + empty state or selectable rows. */
export function HistoryListCard({
  sessions,
  selectedId,
  onSelect,
  total,
}: {
  sessions: SessionHistoryItem[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  total: number;
}) {
  const t = useT("history");
  return (
    <div className="surface-card overflow-hidden">
      <div className="flex items-center justify-between border-b border-surface-border px-4 py-3">
        <h2 className="text-[13px] font-semibold tracking-tight text-ink">{t("list.allSessions")}</h2>
        <span className="chip chip-gray">{t("list.total", { count: total })}</span>
      </div>

      {sessions.length === 0 ? (
        <div className="empty-state !py-14">
          <div className="empty-state-icon">
            <BarChart3 size={22} />
          </div>
          <p className="mb-4 text-[13px]">{t("list.empty")}</p>
          <Link href="/interview" className="btn-primary !h-9">
            <Play size={13} />
            {t("list.startCta")}
          </Link>
        </div>
      ) : (
        <ul className="divide-y divide-surface-border">
          {sessions.map((s) => {
            const active = selectedId === s.id;
            const when = s.created_at ?? s.started_at;
            return (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => onSelect(s.id)}
                  className={`flex w-full items-start gap-3 px-4 py-3.5 text-left transition-colors ${
                    active ? "bg-[var(--info-soft)]" : "hover:bg-surface-alt"
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[13px] font-medium text-ink">
                        {s.role} · {s.level}
                      </span>
                      <StatusBadge status={s.status} />
                      <RoundBadge roundNo={s.round_no} />
                      <ResultBadge result={s.result} />
                      {s.ledger_frozen && (
                        <span className="chip chip-green">{t("list.ledgerBadge")}</span>
                      )}
                    </div>
                    <p className="mt-1 text-[11px] text-ink-subtle">
                      {s.company} · {s.workflow_type}
                      {when ? ` · ${formatDateTime(when)}` : ""}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    {s.overall_score != null && (
                      <p className="font-mono text-[18px] font-semibold leading-none text-[var(--primary)] num-tabular">
                        {s.overall_score}
                      </p>
                    )}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
