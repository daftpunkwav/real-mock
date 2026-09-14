"use client";

import Link from "next/link";
import { useT } from "@/i18n";

/** Growth completion card: progress bar + guidance button. */
export function GrowthProgressCard({ growthPct }: { growthPct: number }) {
  const t = useT("growth");
  return (
    <div className="surface-card p-5">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[13px] font-medium text-ink">{t("progress.title")}</span>
        <span className="font-mono text-[13px] font-semibold text-[var(--primary)] num-tabular">
          {growthPct}%
        </span>
      </div>
      <div className="progress">
        <div
          className="progress-bar"
          style={{
            background:
              "linear-gradient(90deg, var(--chart-3), var(--chart-2))",
            width: `${growthPct}%`,
          }}
        />
      </div>
      <p className="mt-2.5 text-[11px] leading-relaxed text-ink-subtle">
        {t("progress.hint")}
      </p>
      <div className="mt-4 grid grid-cols-2 gap-2">
        <Link href="/interview" className="btn-secondary !h-9 !text-xs">
          {t("progress.interviewCta")}
        </Link>
        <Link href="/prep" className="btn-secondary !h-9 !text-xs">
          {t("progress.prepCta")}
        </Link>
      </div>
    </div>
  );
}
