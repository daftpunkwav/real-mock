"use client";

import { Mic, Video } from "lucide-react";
import { useT } from "@/i18n";

export function HeroInterviewPreview() {
  const t = useT("home");

  return (
    <div className="relative">
      <div
        className="absolute -inset-4 rounded-xl opacity-60 blur-2xl"
        style={{
          background:
            "radial-gradient(ellipse at 50% 80%, color-mix(in srgb, var(--primary) 18%, transparent), transparent 70%)",
        }}
      />
      <div className="surface-card relative overflow-hidden">
        {/* top bar */}
        <div className="flex items-center justify-between border-b border-surface-border bg-surface-alt px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--success)] opacity-40" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--success)]" />
            </span>
            <span className="text-xs font-medium text-ink">{t("hero.preview.status")}</span>
            <span className="chip chip-green !text-[10px]">{t("hero.preview.live")}</span>
          </div>
          <span className="font-mono text-[11px] tracking-wider text-ink-subtle">12:34</span>
        </div>

        {/* dialogue */}
        <div className="space-y-3 p-4 sm:p-5">
          {/* interviewer */}
          <div className="flex gap-3">
            <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--info-soft)] text-[11px] font-semibold text-[var(--info-ink)]">
              {t("hero.preview.interviewerInitial")}
            </div>
            <div className="min-w-0 flex-1">
              <div className="mb-1 flex items-center gap-2">
                <span className="text-[11px] font-medium text-ink">{t("hero.preview.interviewer")}</span>
                <span className="chip chip-blue !text-[10px]">{t("hero.preview.role")}</span>
              </div>
              <div className="rounded-md rounded-tl-sm border border-surface-border bg-surface-alt px-3 py-2.5">
                <p className="text-[13px] leading-relaxed text-ink-muted">
                  {t("hero.preview.question")}
                </p>
              </div>
            </div>
          </div>

          {/* candidate */}
          <div className="flex flex-row-reverse gap-3">
            <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--primary)] text-[11px] font-semibold text-white">
              {t("hero.preview.candidateInitial")}
            </div>
            <div className="min-w-0 flex-1">
              <p className="mb-1 text-right text-[11px] font-medium text-ink-subtle">{t("hero.preview.you")}</p>
              <div className="rounded-md rounded-tr-sm border border-[color-mix(in_srgb,var(--primary)_22%,var(--border))] bg-[var(--info-soft)] px-3 py-2.5">
                <p className="text-[13px] leading-relaxed text-[var(--info-ink)]">
                  {t("hero.preview.answer")}
                </p>
                <span className="mt-1.5 inline-block h-3 w-[2px] animate-pulse bg-[var(--primary)] align-middle" />
              </div>
            </div>
          </div>
        </div>

        {/* bottom bar */}
        <div className="flex items-center gap-4 border-t border-surface-border bg-surface-alt px-4 py-2">
          <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
            <Video size={11} className="text-[var(--primary)]" />
            {t("hero.preview.videoStatus")}
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
            <Mic size={11} className="text-[var(--success)]" />
            {t("hero.preview.micStatus")}
          </div>
        </div>
      </div>
    </div>
  );
}
