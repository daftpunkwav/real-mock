"use client";

import { useT } from "@/i18n";
import { Flag, Radio, Volume2, WifiOff } from "lucide-react";
import { cn } from "@/lib/utils";
import { turnLabelKey } from "../turnLabels";
import type { InterviewRoomModel } from "../hooks/room";

/** Audio Unlock Mask / Broken Bar / Silent Bar / Top Bar (Conversation Info + Talk Wheel + End Button). */
export function InterviewRoomChrome({ room }: { room: InterviewRoomModel }) {
  const {
    sessionId,
    phaseLabels,
    currentPhase,
    currentPhaseTitle,
    planSteps,
    turnState,
    connected,
    connectionState,
    reconnectAttempt,
    audioUnlocked,
    audioBlocked,
    handleEnableAudio,
    finishingUi,
    handleFinish,
  } = room;
  const t = useT("interview");
  const turnLabel = turnLabelKey(turnState);
  // Single current-step display (no plan disclosure, no step index):
  // server-sent title (flow language) > plan step title > static phase label.
  const planStepTitle = planSteps.find((s) => s.id === currentPhase)?.title;
  const currentStepLabel =
    currentPhaseTitle ||
    planStepTitle ||
    phaseLabels[currentPhase] ||
    currentPhase ||
    t("room.phase.preparing");

  return (
    <>
      {!audioUnlocked && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-[var(--background)]/85 p-6 backdrop-blur-md">
          <div className="max-w-sm w-full rounded-lg border border-surface-border bg-surface-card px-6 py-8 text-center shadow-lg">
            <span className="icon-badge icon-badge-brand mx-auto mb-3 !h-12 !w-12">
              <Volume2 size={20} strokeWidth={1.75} />
            </span>
            <h2 className="text-[18px] font-semibold tracking-tight text-ink">{t("room.audio.unlockTitle")}</h2>
            <p className="mt-2 text-[13px] leading-relaxed text-ink-muted">
              {t("room.audio.unlockDesc")}
            </p>
            <button
              type="button"
              onClick={() => void handleEnableAudio()}
              className="btn-primary mt-5 w-full !h-10"
            >
              {t("room.audio.unlockButton")}
            </button>
          </div>
        </div>
      )}
      {!connected && (
        <div className="absolute inset-x-0 top-0 z-30 flex items-center justify-center gap-2 border-b border-[var(--warning)]/30 bg-[var(--warning-soft)] px-3 py-2 text-[var(--warning-ink)] text-xs font-medium shadow-sm">
          {connectionState === "failed" ? (
            <>
              <WifiOff size={14} />
              {t("room.conn.disconnected")}
              <button
                type="button"
                onClick={() => room.retryNow()}
                className="ml-2 underline underline-offset-2 hover:opacity-80"
              >
                {t("room.conn.retry")}
              </button>
            </>
          ) : (
            <>
              <span className="block h-3 w-3 anim-spin rounded-full border-2 border-current border-t-transparent" />
              {t("room.conn.reconnecting")}
              {reconnectAttempt > 0 ? t("room.conn.attempt", { n: reconnectAttempt }) : ""}
            </>
          )}
        </div>
      )}
      {audioBlocked && (
        <div className="absolute inset-x-0 top-0 z-40 flex items-center justify-center gap-2 border-b border-[var(--danger)]/40 bg-[var(--danger-soft)] px-3 py-2 text-[var(--danger-ink)] text-xs font-medium shadow-sm">
          {t("room.audio.blockedBanner")}
          <button
            type="button"
            onClick={() => void handleEnableAudio()}
            className="ml-1 inline-flex items-center gap-1 underline underline-offset-2 hover:opacity-80"
          >
            <Volume2 size={12} />
            {t("room.audio.enableAndRetry")}
          </button>
        </div>
      )}
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-surface-border bg-surface-card/80 px-3 backdrop-blur-md py-2.5 sm:px-4">
        <div className="flex min-w-0 items-center gap-2 text-sm sm:gap-3">
          <span className="shrink-0 font-medium text-ink">{t("room.header.session", { id: sessionId })}</span>
          <span className="truncate rounded-full bg-[var(--info-soft)] px-2 py-0.5 text-xs text-[var(--info-ink)]">
            {currentStepLabel}
          </span>
          <span
            className={cn(
              "hidden sm:inline-flex items-center gap-1 rounded-full border border-surface-border px-2 py-0.5 text-xs",
              turnState === "USER_SPEAKING"
                ? "bg-[var(--success-soft)] text-[var(--success-ink)]"
                : turnState === "AI_SPEAKING"
                  ? "bg-[var(--warning-soft)] text-[var(--warning-ink)]"
                  : "bg-surface-alt text-ink-muted",
            )}
          >
            <Radio
              size={11}
              className={turnState === "USER_SPEAKING" ? "anim-pulse-dot text-[var(--success)]" : "text-ink-subtle"}
            />
            {turnLabel ? t(turnLabel) : turnState}
          </span>
          {audioUnlocked && !audioBlocked && (
            <button
              type="button"
              onClick={() => void handleEnableAudio()}
              className="hidden rounded-full border border-surface-border px-2 py-0.5 text-[11px] text-ink-muted transition-colors hover:bg-surface-alt hover:text-ink md:inline-flex"
            >
              {t("room.audio.reunlock")}
            </button>
          )}
          {!audioUnlocked && (
            <button
              type="button"
              onClick={() => void handleEnableAudio()}
              className="hidden rounded-full border border-[var(--warning)]/40 px-2 py-0.5 text-[11px] text-[var(--warning-ink)] transition-colors hover:bg-[var(--warning-soft)] md:inline-flex"
            >
              {t("room.audio.enable")}
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={handleFinish}
          disabled={finishingUi}
          className="btn-secondary !text-[var(--danger-ink)] hover:!border-[var(--danger)]/40 hover:!bg-[var(--danger-soft)] shrink-0 !h-8 !text-xs"
        >
          {finishingUi ? (
            <>
              <span className="block h-3 w-3 anim-spin rounded-full border-2 border-current border-t-transparent" />
              {t("room.finish.finishing")}
            </>
          ) : (
            <>
              <Flag size={13} />
              {t("room.finish.button")}
            </>
          )}
        </button>
      </header>
    </>
  );
}
