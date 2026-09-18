"use client";

/** Mock-interview settings: clear the agent-generated question-style brief cache. */

import { useState } from "react";
import { Trash2 } from "lucide-react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { toast } from "@/components/Toast";
import { interviewHttp } from "@/lib/api/interviewHttp";
import { useT } from "@/i18n";

export function InterviewSettingsPanel() {
  const t = useT("settings");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  const clear = async () => {
    setBusy(true);
    try {
      const res = await interviewHttp.clearCompanyBriefs();
      toast.success(t("interviewPanel.cleared", { count: res.cleared }));
      setConfirming(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("interviewPanel.clearFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="surface-card p-4">
        <div className="mb-1 flex items-center gap-2">
          <Trash2 size={16} className="text-[var(--danger)]" />
          <h2 className="text-[14px] font-semibold">{t("interviewPanel.title")}</h2>
        </div>
        <p className="text-[13px] leading-relaxed text-ink-muted">{t("interviewPanel.desc")}</p>
        <button
          type="button"
          className="btn-danger mt-3 text-[13px]"
          onClick={() => setConfirming(true)}
        >
          <Trash2 size={13} /> {t("interviewPanel.clear")}
        </button>
      </div>

      <ConfirmDialog
        open={confirming}
        title={t("interviewPanel.clearConfirmTitle")}
        message={t("interviewPanel.clearConfirmMessage")}
        confirmLabel={t("interviewPanel.clear")}
        cancelLabel={t("confirm.cancel")}
        busy={busy}
        onConfirm={clear}
        onCancel={() => setConfirming(false)}
      />
    </div>
  );
}
