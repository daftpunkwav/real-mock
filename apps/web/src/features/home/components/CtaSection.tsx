"use client";

import { useT } from "@/i18n";
import { FlowItem, useFlowProgress } from "./ScrollFlow";
import { StageButton } from "./StageButton";

/** Closing stage: mirrors the hero — centred type over a pool of light, one
 *  shared CTA button — so the page ends in the same voice it opened with.
 *  The whole block drifts in right-to-left as it scrolls into view. */
export function CtaSection() {
  const t = useT("home");
  const { ref, progress, reduce } = useFlowProgress<HTMLElement>();

  return (
    <section
      ref={ref}
      className="relative mx-auto max-w-[1200px] overflow-hidden px-5 pb-24 pt-20 sm:px-6 sm:pb-32 sm:pt-28 lg:px-8"
    >
      <FlowItem progress={progress} reduce={reduce} className="relative flex flex-col items-center text-center">
        <p className="page-eyebrow">{t("cta.eyebrow")}</p>
        <h2 className="mt-2 text-[clamp(1.6rem,3.4vw,2.3rem)] font-bold leading-[1.12] tracking-[-0.02em] text-ink">
          {t("cta.title")}
        </h2>
        <p className="mt-3 max-w-[46ch] text-[14px] leading-relaxed text-ink-muted sm:text-[15px]">
          {t("cta.desc")}
        </p>
        <div className="mt-8">
          <StageButton href="/interview">{t("cta.action")}</StageButton>
        </div>
      </FlowItem>

      {/* Pool of light under the closing line — centre inside the box so the
          falloff reaches zero before any edge and never reads as a rule. */}
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 h-44"
        aria-hidden
        style={{
          background:
            "radial-gradient(42% 60% at 50% 44%, color-mix(in srgb, var(--primary) 10%, transparent), transparent 68%)",
        }}
      />
    </section>
  );
}
