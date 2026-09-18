"use client";

import { useT } from "@/i18n";
import { TRUST_POINTS } from "../content";
import { FlowItem, useFlowProgress } from "./ScrollFlow";

export function TrustSection() {
  const t = useT("home");
  const { ref, progress, reduce } = useFlowProgress<HTMLElement>();

  return (
    <section
      ref={ref}
      className="relative mx-auto max-w-[1200px] px-5 sm:px-6 lg:px-8 pt-20 sm:pt-28"
    >
      <FlowItem progress={progress} reduce={reduce}>
        <div className="stage-card grid grid-cols-1 gap-5 px-6 py-7 sm:grid-cols-3 sm:gap-0 sm:px-2 sm:py-8">
          {TRUST_POINTS.map((it, i) => (
            <div
              key={it.titleKey}
              className={`flex items-start gap-3 sm:px-6 ${i > 0 ? "sm:border-l sm:border-surface-border" : ""}`}
            >
              <span className={`icon-badge ${it.tint}`}>
                <it.icon size={15} strokeWidth={2} />
              </span>
              <div>
                <p className="text-[14px] font-semibold text-ink">{t(it.titleKey)}</p>
                <p className="mt-1 text-[13px] leading-relaxed text-ink-muted">{t(it.descKey)}</p>
              </div>
            </div>
          ))}
        </div>
      </FlowItem>
    </section>
  );
}
