"use client";

/** Prep empty state with resume picker and start action. */

import { Sparkles } from "lucide-react";
import { useT } from "@/i18n";
import { Select } from "@/components/Select";
import type { ResumePickerItem } from "@/lib/api/contract";

interface PrepEmptyStateProps {
  resumeLoadError: string;
  resumes: ResumePickerItem[];
  resumeId: number | null;
  onResumeChange: (id: number | null) => void;
  prepError: string;
  starting: boolean;
  onStart: () => void;
}

export function PrepEmptyState({
  resumeLoadError,
  resumes,
  resumeId,
  onResumeChange,
  prepError,
  starting,
  onStart,
}: PrepEmptyStateProps) {
  const t = useT("prep");
  return (
    <div className="surface-card flex flex-1 flex-col justify-center overflow-hidden p-8">
      <div className="mx-auto w-full max-w-md space-y-5">
        <div className="text-center">
          <span className="icon-badge icon-badge-brand mx-auto mb-4 !h-14 !w-14">
            <Sparkles size={22} strokeWidth={1.75} />
          </span>
          <h2 className="text-[18px] font-semibold tracking-tight text-ink">
            {t("empty.title")}
          </h2>
          <p className="mt-1.5 text-[13px] text-ink-muted">
            {t("empty.desc")}
          </p>
        </div>

        {resumeLoadError ? (
          <div className="alert alert-error !block text-center">{resumeLoadError}</div>
        ) : resumes.length > 0 ? (
          <div>
            <label className="field-label">{t("empty.resumeLabel")}</label>
            <Select
              ariaLabel={t("empty.resumeLabel")}
              value={resumeId ?? ""}
              options={resumes.map((r) => ({
                value: r.id,
                label: `${r.filename}${r.is_active ? t("empty.resumeActiveSuffix") : ""}`,
              }))}
              onChange={(v) => onResumeChange(Number(v))}
            />
          </div>
        ) : (
          <div className="alert alert-warning !block text-center">
            {t("empty.noResume")}
          </div>
        )}

        {prepError && (
          <div className="alert alert-error !block text-center">{prepError}</div>
        )}

        <button
          type="button"
          onClick={onStart}
          disabled={starting}
          className="btn-primary !h-10 w-full"
        >
          {starting ? (
            <span className="block h-3.5 w-3.5 anim-spin rounded-full border-2 border-current border-t-transparent" />
          ) : (
            <Sparkles size={14} />
          )}
          {starting ? t("empty.starting") : t("empty.start")}
        </button>
      </div>
    </div>
  );
}
