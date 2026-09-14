"use client";

import { useT } from "@/i18n";
import { Check, RefreshCw } from "lucide-react";
import { AvatarStage } from "@/features/avatar";
import type { InterviewRoomModel } from "../hooks/room";

/** Agent-planned flow spine: done / active / pending steps. */
function PlanSpine({ room }: { room: InterviewRoomModel }) {
  const { planSteps, currentPhase } = room;
  if (planSteps.length === 0) return null;
  const activeIdx = Math.max(
    0,
    planSteps.findIndex((s) => s.id === currentPhase),
  );
  return (
    <ol className="mb-3 grid gap-1 shrink-0">
      {planSteps.map((step, i) => {
        const done = i < activeIdx;
        const active = i === activeIdx;
        return (
          <li
            key={step.id}
            className={`flex items-center gap-1.5 text-[11px] ${
              active
                ? "font-semibold text-ink"
                : done
                  ? "text-ink-subtle"
                  : "text-ink-muted"
            }`}
          >
            <span
              className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border text-[9px] ${
                done
                  ? "border-[var(--success)] bg-[var(--success)] text-white"
                  : active
                    ? "border-[var(--primary)] text-[var(--primary)] anim-pulse-dot"
                    : "border-surface-border"
              }`}
            >
              {done ? <Check size={9} strokeWidth={3} /> : i + 1}
            </span>
            <span className="truncate">{step.title}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** Right column: AvatarStage + plan spine + reference outline card. */
export function InterviewRoomOutline({ room }: { room: InterviewRoomModel }) {
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
    phaseLabels,
    currentPhase,
    currentPhaseTitle,
    tokenUsage,
  } = room;
  const t = useT("interview");

  return (
    <div className="grid grid-rows-[minmax(180px,1.4fr)_minmax(120px,0.85fr)] lg:grid-rows-[1.618fr_1fr] gap-2 min-h-0 order-1 lg:order-2">
      <AvatarStage
        avatarId={sessionMeta.avatar_id}
        sceneId={sessionMeta.scene_id}
        emotion={emotion}
        speaking={aiSpeaking}
        audioLevel={audioLevel}
      />
      <div className="rounded-lg border border-surface-border bg-surface-card p-3.5 sm:p-4 overflow-y-auto flex flex-col min-h-0">
        <div className="flex items-center justify-between mb-3 shrink-0 gap-2">
          <h3 className="text-[13px] font-medium text-ink">{t("room.outline.title")}</h3>
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
        </div>
        <PlanSpine room={room} />
        <div className="grid grid-cols-2 gap-2 text-[11px] text-ink-muted mb-3 shrink-0">
          <div className="kpi-card !p-2.5">
            <span className="kpi-label">{t("room.outline.phaseLabel")}</span>
            <p className="mt-1 truncate text-[13px] font-semibold text-ink">
              {currentPhaseTitle || phaseLabels[currentPhase] || t("room.outline.phaseEmpty")}
            </p>
          </div>
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
    </div>
  );
}
