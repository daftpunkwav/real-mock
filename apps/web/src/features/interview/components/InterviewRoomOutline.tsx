"use client";

/**
 * @file InterviewRoomOutline.tsx
 * @description Right-hand container hosting avatar display, reference outline, and live coding whiteboard.
 *
 * Responsibilities:
 * - Render the interactive 3D avatar stage and emotional state indicators.
 * - Tab navigation between reference answer and coding whiteboard: both panes
 *   stay mounted (display toggles) so in-progress whiteboard code survives
 *   switching back and forth.
 * - Surface reference hints, source attributions, and token metrics.
 */

import { useState } from "react";
import { useT } from "@/i18n";
import { Code2, FileText, RefreshCw } from "lucide-react";
import { AvatarStage } from "@/features/avatar";
import { InterviewCodingPanel } from "./InterviewCodingPanel";
import type { InterviewRoomModel } from "../hooks/room";

type OutlineTab = "outline" | "coding";

/** Right column: AvatarStage + reference answer / Live Coding Sandbox as in-place tabs. */
export function InterviewRoomOutline({ room }: { room: InterviewRoomModel }) {
  const [activeTab, setActiveTab] = useState<OutlineTab>("outline");
  const {
    sessionMeta,
    emotion,
    aiSpeaking,
    audioLevel,
    showOutline,
    handleOutlineChange,
    requestHint,
    lastQuestion,
    hintLoading,
    referenceHint,
    lastSources,
    tokenUsage,
  } = room;
  const t = useT("interview");

  const tabButton = (tab: OutlineTab) => {
    const active = activeTab === tab;
    return (
      <button
        type="button"
        onClick={() => setActiveTab(tab)}
        className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-medium transition-colors ${
          active
            ? "bg-[var(--primary-soft)] text-[var(--primary)]"
            : "text-ink-muted hover:text-ink"
        }`}
      >
        {tab === "outline" ? <FileText size={11} /> : <Code2 size={11} />}
        {tab === "outline" ? t("room.outline.tabReference") : t("room.outline.tabCoding")}
      </button>
    );
  };

  return (
    <div className="grid grid-rows-[minmax(180px,1.4fr)_minmax(120px,0.85fr)] lg:grid-rows-[1.618fr_1fr] gap-2 min-h-0 order-1 lg:order-2">
      <AvatarStage
        avatarId={sessionMeta.avatar_id}
        sceneId={sessionMeta.scene_id}
        emotion={emotion}
        speaking={aiSpeaking}
        audioLevel={audioLevel}
      />
      <div className="rounded-lg border border-surface-border bg-surface-card p-3.5 sm:p-4 flex flex-col min-h-0">
        <div className="flex items-center justify-between mb-3 shrink-0 gap-2">
          <div className="flex items-center gap-1" role="tablist">
            {tabButton("outline")}
            {tabButton("coding")}
          </div>
          {activeTab === "outline" && (
            <div className="flex items-center gap-2">
              {showOutline && (
                <button
                  type="button"
                  onClick={() => requestHint(lastQuestion)}
                  disabled={!lastQuestion || hintLoading}
                  className="inline-flex items-center gap-1 rounded-full border border-surface-border px-2 py-0.5 text-[11px] text-ink-muted transition-colors hover:bg-surface-alt hover:text-ink disabled:opacity-40"
                  title={t("room.outline.regenerateTitle")}
                >
                  <RefreshCw size={11} className={hintLoading ? "anim-spin" : ""} />
                  {t("room.outline.regenerate")}
                </button>
              )}
              <label className="flex items-center gap-1.5 text-[11px] text-ink-muted cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="rounded border-surface-border bg-surface-card text-[var(--primary)] focus:ring-[var(--primary)] focus:ring-offset-0"
                  checked={showOutline}
                  onChange={(e) => handleOutlineChange(e.target.checked)}
                />
                {t("room.outline.toggle")}
              </label>
            </div>
          )}
        </div>

        {/* Both panes stay mounted: hiding (display:none) preserves the
            candidate's in-progress whiteboard code across tab switches. */}
        <div
          className={`${
            activeTab === "outline" ? "flex" : "hidden"
          } flex-col flex-1 min-h-0 overflow-y-auto`}
          role="tabpanel"
        >
          <div className="grid grid-cols-1 gap-2 text-[11px] text-ink-muted mb-3 shrink-0">
            <div className="kpi-card !p-2.5">
              <span className="kpi-label">{t("room.outline.replyChars")}</span>
              <p className="mt-1 font-mono text-[13px] font-semibold text-ink num-tabular">
                {tokenUsage}
              </p>
            </div>
          </div>

          {!showOutline && (
            <p className="text-[11px] leading-relaxed text-ink-subtle">
              {t("room.outline.hidden")}
            </p>
          )}
          {showOutline && lastSources.length > 0 && lastSources[0] !== "none" && (
            <p className="mb-2 text-[11px] text-ink-subtle">
              {t("room.outline.sourcesPrefix")}
              {lastSources
                .map((s) =>
                  s === "resume"
                    ? t("room.source.resume")
                    : s === "github"
                      ? t("room.source.github")
                      : s === "company_kb"
                        ? t("room.source.companyKb")
                        : null,
                )
                .filter(Boolean)
                .join(", ")}
            </p>
          )}
          {showOutline && hintLoading && (
            <div className="flex items-center gap-2 text-[11px] text-ink-muted">
              <span className="block h-3.5 w-3.5 anim-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
              {t("room.outline.generating")}
            </div>
          )}
          {showOutline && !hintLoading && referenceHint && (
            <div className="flex-1 overflow-y-auto min-h-0">
              {lastQuestion && (
                <p className="mb-2 line-clamp-2 text-[11px] leading-relaxed text-[var(--info-ink)]">
                  {t("room.outline.forQuestion", { q: lastQuestion })}
                </p>
              )}
              <div className="rounded-md border border-surface-border bg-surface-alt p-3 text-[11px] leading-relaxed text-ink whitespace-pre-wrap">
                {referenceHint}
              </div>
            </div>
          )}
          {showOutline && !hintLoading && !referenceHint && (
            <p className="text-[11px] leading-relaxed text-ink-subtle">
              {t("room.outline.placeholder")}
            </p>
          )}
        </div>

        <div
          className={`${activeTab === "coding" ? "flex" : "hidden"} flex-col flex-1 min-h-0`}
          role="tabpanel"
        >
          <InterviewCodingPanel />
        </div>
      </div>
    </div>
  );
}
