"use client";

/**
 * Per-phase evaluation summary from the report synthesis stage.
 * Pure display component: receives a phase-keyed map from the report page.
 */

import { useT } from "@/i18n";

/** Per-phase one-line evaluations from the synthesis stage. */
export function PhaseOverviewCard({ summary }: { summary?: Record<string, string> }) {
  const t = useT("report");
  const entries = Object.entries(summary ?? {}).filter(([, text]) => text?.trim());
  if (entries.length === 0) return null;
  return (
    <div className="surface-card mt-4 p-4">
      <h3 className="mb-3 text-[13px] font-semibold tracking-tight text-ink">
        {t("sections.phaseOverview")}
      </h3>
      <ul className="space-y-2.5">
        {entries.map(([phase, text]) => (
          <li key={phase} className="flex items-start gap-2.5 text-[13px] leading-relaxed">
            <span className="mt-0.5 shrink-0 rounded-full border border-surface-border bg-surface-alt px-2 py-0.5 text-[11px] text-ink-muted">
              {phase}
            </span>
            <span className="min-w-0 break-words text-ink">{text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
