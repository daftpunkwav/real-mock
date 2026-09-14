"use client";

/**
 * @file CompletionCard.tsx
 * @description Sidebar card showing profile completion percentage and required gaps.
 *
 * Responsibilities:
 * - Display completion progress and required/optional KPI counts
 * - List missing required labels or confirm all required fields are ready
 */

import { CheckCircle2 } from "lucide-react";
import { useT } from "@/i18n";
import { OPTIONAL_COMPLETION_KEYS, type ProfileCompletionStats } from "../profileCompletion";
import { REQUIRED_KEYS, REQUIRED_LABELS } from "../profileRequired";

export function CompletionCard({ stats }: { stats: ProfileCompletionStats }) {
  const t = useT("profile");
  const { completionPct, requiredDone, optionalDone, requiredMissing } = stats;
  const missingLabels = requiredMissing
    .map((k) => t(REQUIRED_LABELS[k]))
    .join(t("format.listSeparator"));
  return (
    <div className="surface-card p-5">
      <div className="mb-2.5 flex items-center justify-between">
        <span className="text-[13px] font-semibold tracking-tight text-ink">
          {t("completion.title")}
        </span>
        <span className="font-mono text-[14px] font-semibold text-[var(--primary)] num-tabular">
          {completionPct}%
        </span>
      </div>
      <div
        className="progress"
        role="progressbar"
        aria-label={t("completion.title")}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={completionPct}
      >
        <div
          className="progress-bar anim-progress-fill"
          style={{ width: `${completionPct}%` }}
        />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-center">
        <div className="kpi-card !p-2.5">
          <p className="font-mono text-[15px] font-semibold text-ink num-tabular">
            {requiredDone}/{REQUIRED_KEYS.length}
          </p>
          <p className="kpi-label mt-0.5">{t("completion.required")}</p>
        </div>
        <div className="kpi-card !p-2.5">
          <p className="font-mono text-[15px] font-semibold text-ink num-tabular">
            {optionalDone}/{OPTIONAL_COMPLETION_KEYS.length}
          </p>
          <p className="kpi-label mt-0.5">{t("completion.optional")}</p>
        </div>
      </div>
      {requiredMissing.length > 0 ? (
        <div className="mt-3 rounded-md border border-[var(--danger)]/30 bg-[var(--danger-soft)] px-3 py-2">
          <p className="text-[11px] leading-relaxed text-[var(--danger-ink)]">
            {t("completion.missingList", { labels: missingLabels })}
          </p>
        </div>
      ) : (
        <div className="mt-3 flex items-center gap-2 rounded-md border border-[var(--success)]/30 bg-[var(--success-soft)] px-3 py-2">
          <CheckCircle2 size={13} className="text-[var(--success)]" />
          <span className="text-[11px] font-medium text-[var(--success-ink)]">
            {t("completion.allReady")}
          </span>
        </div>
      )}
    </div>
  );
}
