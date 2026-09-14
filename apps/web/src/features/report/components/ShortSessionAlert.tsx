"use client";

import { useT } from "@/i18n";

/** Warning banner for short sessions. */
export function ShortSessionAlert({ show }: { show: boolean }) {
  const t = useT("report");
  if (!show) return null;
  return (
    <div className="alert alert-warning mb-6">
      {t("alerts.shortSession")}
    </div>
  );
}
