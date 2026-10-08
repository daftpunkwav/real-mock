"use client";

/** Mock-interview settings: clear the agent-generated question-style brief cache. */

import { Trash2 } from "lucide-react";
import { toast } from "@/components/Toast";
import { interviewHttp } from "@/lib/api/interviewHttp";
import { useT } from "@/i18n";
import { DangerActionCard } from "./DangerActionCard";

export function InterviewSettingsPanel() {
  const t = useT("settings");

  const clear = async () => {
    try {
      const res = await interviewHttp.clearCompanyBriefs();
      toast.success(t("interviewPanel.cleared", { count: res.cleared }));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("interviewPanel.clearFailed"));
      throw e;
    }
  };

  return (
    <DangerActionCard
      icon={<Trash2 size={16} className="text-[var(--danger)]" />}
      title={t("interviewPanel.title")}
      description={t("interviewPanel.desc")}
      actionLabel={t("interviewPanel.clear")}
      confirmTitle={t("interviewPanel.clearConfirmTitle")}
      confirmBody={t("interviewPanel.clearConfirmMessage")}
      actionIcon={<Trash2 size={13} />}
      onConfirm={clear}
    />
  );
}
