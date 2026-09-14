"use client";

/**
 * @file ResumeOverviewCard.tsx
 * @description Sticky KPI card: uploaded count, scored count, active filename.
 */

import { Gauge } from "lucide-react";
import type { Resume } from "../types";
import { useT } from "@/i18n";

/** Sticky KPI card (resume/uploaded/scored counts, active file). */
export function ResumeOverviewCard({ resumes }: { resumes: Resume[] }) {
  const t = useT("resume");
  const activeResume = resumes.find((r) => r.is_active);
  return (
    <div className="surface-card p-4 sm:p-5">
      <h2 className="mb-3 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
        <Gauge size={14} className="text-[var(--warning)]" />
        {t("overviewCard.title")}
      </h2>
      <div className="grid grid-cols-2 gap-2">
        <div className="kpi-card !p-3">
          <p className="kpi-value !text-xl">{resumes.length}</p>
          <p className="kpi-label mt-1">{t("overviewCard.uploaded")}</p>
        </div>
        <div className="kpi-card !p-3">
          <p className="kpi-value !text-xl">{resumes.filter((r) => r.score != null).length}</p>
          <p className="kpi-label mt-1">{t("overviewCard.scored")}</p>
        </div>
      </div>
      {activeResume && (
        <p className="mt-3 border-t border-surface-border pt-3 text-[11px] leading-relaxed text-ink-subtle">
          {t("overviewCard.active")}
          <span className="ml-1 font-medium text-ink">{activeResume.filename}</span>
        </p>
      )}
    </div>
  );
}
