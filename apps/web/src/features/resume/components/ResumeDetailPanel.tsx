"use client";

/**
 * @file ResumeDetailPanel.tsx
 * @description Deep-review pane: empty, in-flight, or AnalysisPanel.
 */

import { Sparkles } from "lucide-react";
import type { Resume, ResumeAnalysis } from "../types";
import { Spinner } from "@/components/Spinner";
import { useT } from "@/i18n";
import { AnalysisPanel } from "./AnalysisPanel";
import { AnalyzeStageProgress } from "./AnalyzeStageProgress";
import type { ReviewLiveState } from "../reviewProgress";

interface ResumeDetailPanelProps {
  resume: Resume | null;
  analysis: ResumeAnalysis | null;
  familyRows?: Resume[];
  analyzingIds: number[];
  analyzeProgress?: ReviewLiveState;
  error: string;
  onAnalyze: (id: number) => void;
}

export function ResumeDetailPanel({
  resume: previewResume,
  analysis,
  familyRows = [],
  analyzingIds,
  analyzeProgress,
  error,
  onAnalyze,
}: ResumeDetailPanelProps) {
  const t = useT("resume");
  const analyzingThis = previewResume != null && analyzingIds.includes(previewResume.id);
  return (
    <section className="surface-card overflow-hidden">
      {analyzingThis && (
        <div className="flex items-center gap-2.5 border-b border-surface-border bg-[var(--info-soft)] px-5 py-3 text-[13px] text-[var(--info-ink)] sm:px-7">
          <Spinner className="h-3.5 w-3.5" />
          <span className="tracking-[0.02em]">{t("detail.analyzingBanner")}</span>
        </div>
      )}
      <div className={analyzingThis ? "p-0" : "px-5 pb-6 pt-6 sm:px-8 sm:pb-8 sm:pt-7"}>
        {!previewResume ? (
          <div className="empty-state !py-10">
            <p className="text-[13px] tracking-[0.04em]">{t("detail.emptySelect")}</p>
          </div>
        ) : analyzingThis ? (
          <AnalyzeStageProgress progress={analyzeProgress} />
        ) : !analysis ? (
          <div className="py-12 text-center">
            <div className="empty-state-icon mx-auto mb-4">
              <Sparkles size={20} />
            </div>
            <p className="mb-1.5 text-[13px] tracking-[0.04em] text-ink-muted">
              {t("detail.none")}
            </p>
            <p className="mx-auto mb-5 max-w-sm text-[11px] leading-relaxed tracking-[0.03em] text-ink-subtle">
              {t("detail.noneHint")}
            </p>
            {error && (
              <p className="mx-auto mb-4 max-w-md text-[11px] leading-relaxed text-[var(--danger-ink)]">
                {error}
              </p>
            )}
            <button
              type="button"
              onClick={() => onAnalyze(previewResume.id)}
              disabled={analyzingThis}
              className="btn-primary !h-9"
            >
              <Sparkles size={13} />
              {t("detail.start")}
            </button>
          </div>
        ) : (
          <>
            {error && (
              <div className="alert alert-warning mb-4 text-xs">{error}</div>
            )}
            <AnalysisPanel
              analysis={analysis}
              familyRows={familyRows}
              currentId={previewResume.id}
            />
          </>
        )}
      </div>
    </section>
  );
}
