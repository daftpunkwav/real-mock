"use client";

import { useT } from "@/i18n";

/** Interview presence analysis card. */
export function FaceAnalysisCard({ summary }: { summary: string }) {
  const t = useT("report");
  return (
    <div className="surface-card p-4">
      <h3 className="mb-2 text-[13px] font-semibold tracking-tight text-ink">
        {t("face.title")}
      </h3>
      <p className="text-[13px] leading-relaxed text-ink-muted">
        {summary}
      </p>
    </div>
  );
}
