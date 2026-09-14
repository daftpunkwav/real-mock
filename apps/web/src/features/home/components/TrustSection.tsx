"use client";

import { TRUST_POINTS } from "../content";
import { useT } from "@/i18n";

export function TrustSection() {
  const t = useT("home");
  return (
    <section className="bg-surface">
      <div className="mx-auto max-w-[1320px] px-5 sm:px-6 lg:px-10 py-10 sm:py-14">
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-3 sm:gap-0">
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
      </div>
    </section>
  );
}
