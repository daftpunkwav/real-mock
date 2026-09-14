"use client";

/**
 * @file ResumeTipsCard.tsx
 * @description Sticky tips for writing a stronger resume.
 */

import { Lightbulb } from "lucide-react";
import { useT } from "@/i18n";

/** Sticky writing-tips card (title + three tips). */
export function ResumeTipsCard() {
  const t = useT("resume");
  return (
    <div className="surface-card p-4 sm:p-5">
      <h2 className="mb-2.5 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
        <Lightbulb size={14} className="text-[var(--primary)]" />
        {t("tips.title")}
      </h2>
      <ul className="space-y-2 text-[11px] leading-relaxed text-ink-subtle">
        <li>{t("tips.first")}</li>
        <li>{t("tips.second")}</li>
        <li>{t("tips.third")}</li>
      </ul>
    </div>
  );
}
