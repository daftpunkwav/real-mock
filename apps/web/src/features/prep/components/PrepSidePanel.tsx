"use client";

/**
 * @file PrepSidePanel.tsx
 * @description Prep right rail: linked resume summary, session history with
 * background-generation badges, and quick prompts ("#" reference chips live
 * in PrepComposer). Hidden below the lg breakpoint.
 */

import { FileText, Zap } from "lucide-react";
import { useT } from "@/i18n";
import { Select } from "@/components/Select";
import { PREP_QUICK_PROMPT_KEYS } from "@/config/prepPrompts";
import type { PrepSessionSummary, ResumePickerItem } from "@/lib/api/contract";
import { PrepSessionList } from "./PrepSessionList";

interface PrepSidePanelProps {
  selectedResume: ResumePickerItem | null;
  resumes: ResumePickerItem[];
  resumeId: number | null;
  onResumeChange: (id: number | null) => void;
  sessions: PrepSessionSummary[];
  prepSessionId: number | null;
  starting: boolean;
  busySids: readonly number[];
  /** AI-generated follow-ups from the latest exchange; null keeps the defaults. */
  quickSuggestions: string[] | null;
  onSelectSession: (id: number) => void;
  onNewSession: () => void;
  onQuickPrompt: (prompt: string) => void;
  onDeleteSession: (id: number) => void;
  onArchiveSession: (id: number, archived: boolean) => void;
  onClearSession: (id: number) => void;
  onStopSession: (id: number) => void;
}

export function PrepSidePanel({
  selectedResume,
  resumes,
  resumeId,
  onResumeChange,
  sessions,
  prepSessionId,
  starting,
  busySids,
  quickSuggestions,
  onSelectSession,
  onNewSession,
  onQuickPrompt,
  onDeleteSession,
  onArchiveSession,
  onClearSession,
  onStopSession,
}: PrepSidePanelProps) {
  const t = useT("prep");
  return (
    <div className="hidden min-h-0 flex-col gap-3 overflow-y-auto pr-0.5 [scrollbar-gutter:stable] lg:flex">
      <div className="surface-card p-4">
        <h2 className="mb-3 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
          <FileText size={14} className="text-[var(--primary)]" />
          {t("panel.resumeTitle")}
        </h2>
        {resumes.length > 0 ? (
          <>
            <Select
              ariaLabel={t("panel.resumeTitle")}
              value={resumeId ?? ""}
              options={resumes.map((r) => ({
                value: r.id,
                label: `${r.filename}${r.is_active ? t("empty.resumeActiveSuffix") : ""}`,
              }))}
              onChange={(v) => onResumeChange(Number(v))}
            />
            {selectedResume && (
              <p className="mt-1.5 text-[11px] text-ink-subtle">
                {selectedResume.is_active ? t("panel.resumeActive") : t("panel.resumeInactive")}
                {selectedResume.score != null && t("panel.resumeScore", { score: selectedResume.score })}
              </p>
            )}
          </>
        ) : (
          <p className="text-[12px] text-ink-subtle">{t("panel.noResume")}</p>
        )}
      </div>

      <div className="surface-card p-4">
        <PrepSessionList
          sessions={sessions}
          currentId={prepSessionId}
          creating={starting}
          busySids={busySids}
          onSelect={onSelectSession}
          onNew={onNewSession}
          onDelete={onDeleteSession}
          onArchive={onArchiveSession}
          onClear={onClearSession}
          onStop={onStopSession}
        />
      </div>

      <div className="surface-card p-4">
        <h2 className="mb-3 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
          <Zap size={14} className="text-[var(--warning)]" />
          {t("panel.quickPrompts")}
        </h2>
        <div className="space-y-1.5">
          {(quickSuggestions && quickSuggestions.length > 0
            ? quickSuggestions
            : PREP_QUICK_PROMPT_KEYS.map((key) => t(key))
          ).map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => onQuickPrompt(prompt)}
              className="w-full rounded-md border border-surface-border px-3 py-2 text-left text-[12px] leading-relaxed text-ink-muted transition-colors hover:border-[var(--primary)] hover:bg-[var(--info-soft)] hover:text-ink"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
