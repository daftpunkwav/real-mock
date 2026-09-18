"use client";

import { ArrowRight } from "lucide-react";
import { useT } from "@/i18n";
import { PAIN_POINTS } from "../content";
import { FlowItem, useFlowProgress } from "./ScrollFlow";

/* A small vignette per failure mode, painted in the card's danger tint —
   the same evidence-block language as the hero ring cards. */
function painGraphic(index: number): React.ReactNode {
  const ink = "var(--danger-ink)";
  const soft = "color-mix(in srgb, var(--danger-ink) 38%, transparent)";
  const faint = "color-mix(in srgb, var(--danger-ink) 16%, transparent)";
  switch (index) {
    case 0:
      // A fixed question bank: identical rows, the last one crossed out.
      return (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="h-1.5 flex-1 rounded-full" style={{ background: i === 2 ? soft : faint }} />
              <svg width="9" height="9" viewBox="0 0 9 9" className="shrink-0" style={{ opacity: i === 2 ? 1 : 0 }}>
                <path d="M1 1l7 7M8 1L1 8" stroke={ink} strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </div>
          ))}
        </div>
      );
    case 1:
      // Practising blind: the question goes out, the feedback box stays empty.
      return (
        <div className="flex items-center gap-3">
          <div className="flex-1 space-y-1.5">
            <div className="h-1.5 w-full rounded-full" style={{ background: faint }} />
            <div className="h-1.5 w-3/5 rounded-full" style={{ background: soft }} />
          </div>
          <svg width="14" height="8" viewBox="0 0 14 8" className="shrink-0">
            <path d="M0 4h11M8 1l3 3-3 3" stroke={soft} strokeWidth="1.4" fill="none" strokeLinecap="round" />
          </svg>
          <div
            className="h-9 flex-1 rounded-md border border-dashed"
            style={{ borderColor: soft }}
          />
        </div>
      );
    default:
      // Stage fright: a voice waveform that dies out mid-answer.
      return (
        <div className="flex h-9 items-end gap-1">
          {[22, 30, 26, 18, 12, 8, 5, 3, 2].map((h, i) => (
            <div
              key={i}
              className="w-1.5 rounded-full"
              style={{ height: h, background: ink, opacity: 1 - i * 0.1 }}
            />
          ))}
          <div className="ml-1 h-1.5 flex-1 rounded-full" style={{ background: faint }} />
        </div>
      );
  }
}

/** Why mock interviews usually fail — three failure modes, each with the answer.
    Cards stream in right-to-left as the section scrolls into view. */
export function PainSection() {
  const t = useT("home");
  const { ref, progress, reduce } = useFlowProgress<HTMLElement>();

  return (
    <section
      ref={ref}
      className="relative mx-auto max-w-[1200px] px-5 sm:px-6 lg:px-8 pt-20 sm:pt-28"
    >
      <FlowItem progress={progress} reduce={reduce} className="mx-auto max-w-[62ch] text-center">
        <p className="page-eyebrow">{t("pain.eyebrow")}</p>
        <h2 className="page-title sm:!text-[30px]">{t("pain.title")}</h2>
        <p className="page-desc mx-auto">{t("pain.desc")}</p>
      </FlowItem>

      <div className="mt-12 grid grid-cols-1 gap-4 md:grid-cols-3 md:gap-5">
        {PAIN_POINTS.map(({ icon: Icon, titleKey, descKey, featureKey }, i) => (
          <FlowItem key={titleKey} progress={progress} reduce={reduce} index={i + 1}>
            <div className="stage-card flex h-full flex-col p-6">
              <div className="flex items-center gap-2.5">
                <span className="font-mono text-[11px] font-semibold tracking-[0.14em] text-[var(--danger-ink)]">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="h-px flex-1 bg-surface-border" />
                <span className="icon-badge icon-badge-danger !h-7 !w-7">
                  <Icon size={14} strokeWidth={1.75} />
                </span>
              </div>
              <h3 className="mt-4 text-[16px] font-semibold text-ink">{t(titleKey)}</h3>
              <p className="mt-1.5 text-[13px] leading-relaxed text-ink-muted">{t(descKey)}</p>
              <div className="mt-5">{painGraphic(i)}</div>
              <p className="mt-auto flex items-center gap-1.5 border-t border-surface-border pt-3.5 text-[12px] font-medium text-[var(--primary)]">
                <ArrowRight size={12} className="shrink-0" />
                {t(featureKey)}
              </p>
            </div>
          </FlowItem>
        ))}
      </div>
    </section>
  );
}
