"use client";

import Link from "next/link";
import { Award, Play } from "lucide-react";
import type { GrowthRecord } from "@/types";
import { formatDateTime, useT } from "@/i18n";
import { Section } from "./Section";

/** Training history block: records are listed by session, and the empty state guides the start of the interview. */
export function TrainingHistorySection({
  records,
  selectedId,
  onSelect,
}: {
  records: GrowthRecord[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const t = useT("growth");
  return (
    <Section title={t("history.title")} icon={Award}>
      {records.length > 0 ? (
        <div className="space-y-2">
          {records.map((r) => {
            const active = selectedId === r.id;
            return (
              <button
                key={r.id}
                type="button"
                onClick={() => onSelect(r.id)}
                className={`w-full rounded-md border px-4 py-3.5 text-left transition-colors ${
                  active
                    ? "border-[var(--primary)] bg-[var(--info-soft)]"
                    : "border-surface-border hover:border-surface-strong hover:bg-surface-alt"
                }`}
              >
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="text-[13px] font-semibold text-ink">
                    {t("history.session", { id: r.session_id })}
                  </span>
                  <Link
                    href={`/report/${r.session_id}`}
                    onClick={(e) => e.stopPropagation()}
                    className="text-[11px] font-medium text-[var(--primary)] hover:underline"
                  >
                    {t("history.report")}
                  </Link>
                </div>
                <p className="mb-2 text-[11px] text-ink-subtle">
                  {formatDateTime(r.created_at)}
                </p>
                {r.weak_skills.length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-1">
                    {r.weak_skills.map((s) => (
                      <span key={s} className="chip chip-red !text-[10px]">
                        {s}
                      </span>
                    ))}
                  </div>
                )}
                {r.training_plan.length > 0 && (
                  <p className="line-clamp-2 text-[11px] leading-relaxed text-ink-muted">
                    {r.training_plan[0]}
                  </p>
                )}
              </button>
            );
          })}
        </div>
      ) : (
        <div className="py-10 text-center">
          <Award className="mx-auto mb-3 text-ink-subtle" size={28} />
          <p className="mb-4 text-[13px] text-ink-subtle">{t("history.empty")}</p>
          <Link href="/interview" className="btn-primary !h-9">
            <Play size={13} />
            {t("history.startCta")}
          </Link>
        </div>
      )}
    </Section>
  );
}
