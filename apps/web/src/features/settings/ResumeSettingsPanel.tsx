"use client";

/**
 * @file ResumeSettingsPanel.tsx
 * @description Resume category: destructive resume-collection clears behind confirm dialogs.
 */

import { TriangleAlert } from "lucide-react";
import { toast } from "@/components/Toast";
import { useT } from "@/i18n";
import { formatApiError } from "@/lib/api/base";
import { DangerActionCard } from "./DangerActionCard";
import { useDataClear, type DataClearKind } from "./useDataClear";

export function ResumeSettingsPanel() {
  const t = useT("settings");
  const { busy, run } = useDataClear();

  const handleRun = async (kind: DataClearKind) => {
    try {
      const count = await run(kind);
      toast.success(
        t(kind === "results" ? "data.clearResults.done" : "data.clearAll.done", {
          count,
        }),
      );
    } catch (err) {
      const fallback = t(kind === "results" ? "data.clearResults.failed" : "data.clearAll.failed");
      toast.error(err instanceof Error ? formatApiError(err) : fallback);
      throw err;
    }
  };

  return (
    <div className="space-y-4">
      <DangerActionCard
        icon={<TriangleAlert size={16} className="text-[var(--danger)]" />}
        title={t("data.clearResults.title")}
        description={t("data.clearResults.desc")}
        actionLabel={t("data.clearResults.action")}
        confirmTitle={t("data.clearResults.confirmTitle")}
        confirmBody={t("data.clearResults.confirmBody")}
        disabled={busy !== null}
        onConfirm={() => handleRun("results")}
      />
      <DangerActionCard
        icon={<TriangleAlert size={16} className="text-[var(--danger)]" />}
        title={t("data.clearAll.title")}
        description={t("data.clearAll.desc")}
        actionLabel={t("data.clearAll.action")}
        confirmTitle={t("data.clearAll.confirmTitle")}
        confirmBody={t("data.clearAll.confirmBody")}
        disabled={busy !== null}
        onConfirm={() => handleRun("collection")}
      />
    </div>
  );
}
