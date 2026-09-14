"use client";

/**
 * @file ResumeSettingsPanel.tsx
 * @description Resume category: destructive resume-collection clears behind confirm dialogs.
 */

import { TriangleAlert } from "lucide-react";
import { useState } from "react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { toast } from "@/components/Toast";
import { useT } from "@/i18n";
import { formatApiError } from "@/lib/api/base";
import { useDataClear, type DataClearKind } from "./useDataClear";

function DangerCard({
  title,
  desc,
  action,
  confirmTitle,
  confirmBody,
  kind,
  disabled,
  onRun,
}: {
  title: string;
  desc: string;
  action: string;
  confirmTitle: string;
  confirmBody: string;
  kind: DataClearKind;
  disabled: boolean;
  /** Runs the mutation; must throw on failure so the dialog stays open. */
  onRun: (kind: DataClearKind) => Promise<void>;
}) {
  const tc = useT("common");
  const [confirming, setConfirming] = useState(false);
  const [running, setRunning] = useState(false);

  const handleConfirm = async () => {
    setRunning(true);
    try {
      await onRun(kind);
      setConfirming(false);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="surface-card p-4">
      <div className="mb-1 flex items-center gap-2">
        <TriangleAlert size={16} className="text-[var(--danger)]" />
        <h2 className="text-[14px] font-semibold">{title}</h2>
      </div>
      <p className="text-[13px] leading-relaxed text-ink-muted">{desc}</p>
      <button
        type="button"
        disabled={disabled || running}
        onClick={() => setConfirming(true)}
        className="mt-3 inline-flex h-9 items-center rounded-md border border-[var(--danger)]/30 bg-surface-alt px-4 text-[13px] font-medium text-[var(--danger-ink)] transition-colors hover:bg-[var(--danger-soft)] disabled:cursor-not-allowed disabled:opacity-45"
      >
        {action}
      </button>
      <ConfirmDialog
        open={confirming}
        title={confirmTitle}
        message={confirmBody}
        confirmLabel={action}
        cancelLabel={tc("confirm.cancel")}
        busy={running}
        onConfirm={() => void handleConfirm()}
        onCancel={() => setConfirming(false)}
      />
    </div>
  );
}

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
      const fallback = t(
        kind === "results" ? "data.clearResults.failed" : "data.clearAll.failed",
      );
      toast.error(err instanceof Error ? formatApiError(err) : fallback);
      throw err;
    }
  };

  return (
    <div className="space-y-4">
      <DangerCard
        title={t("data.clearResults.title")}
        desc={t("data.clearResults.desc")}
        action={t("data.clearResults.action")}
        confirmTitle={t("data.clearResults.confirmTitle")}
        confirmBody={t("data.clearResults.confirmBody")}
        kind="results"
        disabled={busy !== null}
        onRun={handleRun}
      />
      <DangerCard
        title={t("data.clearAll.title")}
        desc={t("data.clearAll.desc")}
        action={t("data.clearAll.action")}
        confirmTitle={t("data.clearAll.confirmTitle")}
        confirmBody={t("data.clearAll.confirmBody")}
        kind="collection"
        disabled={busy !== null}
        onRun={handleRun}
      />
    </div>
  );
}
