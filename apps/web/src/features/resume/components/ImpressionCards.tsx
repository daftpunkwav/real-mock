"use client";

/**
 * @file ImpressionCards.tsx
 * @description Headline, first-impression, and interviewer-comment cards.
 */

import { MessagesSquare, Quote, ScanFace } from "lucide-react";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { useT } from "@/i18n";
import { percentileColor } from "@/lib/scoreColor";
import { EvalRichText } from "./EvalRichText";
import { useInViewReveal } from "../useInViewReveal";

/** Headline banner with normalized punctuation; null when empty. */
export function HeadlineBanner({ text }: { text: string }) {
  const t = useT("resume");
  const cn = normalizeCnPunctuation(text.trim());
  if (!cn) return null;
  return (
    <div className="flex items-stretch gap-3.5">
      <span className="w-1 shrink-0 rounded-full bg-gradient-to-b from-[var(--primary)] to-[var(--primary)]/25" />
      <div className="min-w-0">
        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-ink-subtle">
          {t("overview.headlineTag")}
        </p>
        <p className="mt-1 text-[17px] font-semibold leading-snug tracking-tight text-ink sm:text-[19px]">
          {cn}
        </p>
      </div>
    </div>
  );
}

/** First-impression quote card; null when empty. */
export function FirstImpressionCard({ text }: { text: string }) {
  const t = useT("resume");
  const cn = normalizeCnPunctuation(text.trim());
  if (!cn) return null;
  return (
    <div className="eval-impression">
      <Quote size={44} className="eval-impression-quote" aria-hidden />
      <div className="relative min-w-0">
        <p className="mb-2.5 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--primary-ink)]">
          <ScanFace size={13} />
          {t("overview.impressionTag")}
        </p>
        <p className="eval-impression-body">
          <EvalRichText text={cn} />
        </p>
      </div>
    </div>
  );
}

/** Tilted interviewer-note cards; null when empty. */
export function InterviewerNotes({ items }: { items: string[] }) {
  const t = useT("resume");
  const cleaned = items.map((s) => normalizeCnPunctuation(String(s).trim())).filter(Boolean);
  if (cleaned.length === 0) return null;
  return (
    <section className="eval-section">
      <span className="eval-label">{t("overview.notesTitle")}</span>
      <div className="eval-notes-grid">
        {cleaned.map((s, i) => (
          <div key={i} className={`eval-note ${i % 2 === 0 ? "is-tilt-l" : "is-tilt-r"}`}>
            <Quote size={12} className="shrink-0 text-[var(--primary)]" aria-hidden />
            <p className="min-w-0">
              <EvalRichText text={s} />
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

/** Percentile bar with a positioned pin. */
export function PercentileBar({ pct }: { pct: number }) {
  const t = useT("resume");
  const { ref, shown } = useInViewReveal();

  const clamped = Math.max(0, Math.min(100, Math.round(pct)));
  const color = percentileColor(clamped);

  return (
    <div ref={ref} className="eval-percentile">
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-ink-subtle">
          <MessagesSquare size={12} />
          {t("overview.percentileTitle")}
        </p>
        <p className="text-[12px] text-ink-muted">
          {t("overview.percentileBefore")}
          <strong className="mx-1 num-tabular text-[15px]" style={{ color }}>
            {clamped}%
          </strong>
          {t("overview.percentileAfter")}
        </p>
      </div>
      <div className="eval-percentile-track">
        <div className="eval-percentile-fill" aria-hidden />
        <span
          className="eval-percentile-pin"
          style={{
            left: `${clamped}%`,
            background: color,
            transform: shown ? "translate(-50%, 0) scale(1)" : "translate(-50%, 0) scale(0)",
          }}
        >
          <span className="eval-percentile-pin-val num-tabular">{clamped}</span>
        </span>
      </div>
      <div className="eval-percentile-scale">
        <span>{t("overview.scaleLow")}</span>
        <span>{t("overview.scaleMid")}</span>
        <span>{t("overview.scaleHigh")}</span>
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-ink-subtle">{t("overview.percentileDisclaimer")}</p>
    </div>
  );
}
