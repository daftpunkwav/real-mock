"use client";

import Link from "next/link";
import { ArrowLeft, FileBarChart } from "lucide-react";
import { useT } from "@/i18n";
import { formatScore } from "../scoreFormat";
import { scoreColor } from "@/lib/scoreColor";

/** Report header with back link and overall score. */
export function ScoreSummaryCard({
  duration,
  messagesCount,
  overallScore,
}: {
  duration?: number;
  messagesCount?: number;
  overallScore: number | null | undefined;
}) {
  const t = useT("report");
  return (
    <>
      <Link
        href="/history"
        className="mb-6 flex w-fit items-center gap-1 text-[12px] text-ink-subtle hover:text-[var(--primary)]"
      >
        <ArrowLeft size={13} /> {t("summary.backLink")}
      </Link>

      <div className="surface-card mb-6 flex flex-col justify-between gap-4 p-5 sm:flex-row sm:items-center">
        <div className="flex items-start gap-3">
          <span className="icon-badge icon-badge-brand">
            <FileBarChart size={18} strokeWidth={1.75} />
          </span>
          <div>
            <p className="page-eyebrow">{t("summary.eyebrow")}</p>
            <h1 className="page-title !mt-1">{t("summary.title")}</h1>
            {duration != null && (
              <p className="mt-1.5 text-[12px] text-ink-subtle">
                {t("summary.duration", { duration })}
                {typeof messagesCount === "number"
                  ? t("summary.messagesCount", { count: messagesCount })
                  : ""}
              </p>
            )}
          </div>
        </div>
        <div className="rounded-md border border-surface-border bg-surface-alt px-5 py-3 text-center sm:text-right">
          <div
            className="font-mono text-[36px] font-semibold leading-none tracking-tight num-tabular"
            style={{ color: scoreColor(overallScore) }}
          >
            {formatScore(overallScore)}
          </div>
          <div className="mt-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-subtle">
            {t("summary.overallScore")}
          </div>
        </div>
      </div>
    </>
  );
}
