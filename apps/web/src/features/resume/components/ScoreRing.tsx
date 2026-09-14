"use client";

/**
 * @file ScoreRing.tsx
 * @description Circular overall-score indicator with in-view reveal.
 */

import { useT } from "@/i18n";
import { useInViewReveal } from "../useInViewReveal";
import { bandColor, scoreBand, type ScoreBandId } from "../analysisFormat";

/** i18n key per score band (static map keeps the typed translator happy). */
const BAND_LABEL_KEYS: Record<ScoreBandId, `overview.band.${ScoreBandId}`> = {
  standout: "overview.band.standout",
  solid: "overview.band.solid",
  mixed: "overview.band.mixed",
  weak: "overview.band.weak",
};

/** Animated score ring (0-100, clamped); reveals on first in-view. */
export function ScoreRing({ score, size = 112 }: { score: number; size?: number }) {
  const t = useT("resume");
  const { ref, shown } = useInViewReveal();

  const clamped = Math.max(0, Math.min(100, Math.round(score)));
  const radius = size / 2 - 9;
  const circumference = 2 * Math.PI * radius;
  const progress = shown ? clamped / 100 : 0;
  const ring = bandColor(scoreBand(clamped));

  return (
    <div
      ref={ref}
      className="relative shrink-0"
      style={{ width: size, height: size }}
      role="img"
      aria-label={t("ring.aria", { score: clamped })}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--muted)"
          strokeWidth={8}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={ring}
          strokeWidth={8}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - progress)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{
            transition: "stroke-dashoffset 1.3s cubic-bezier(0.22, 1, 0.36, 1), stroke 0.6s",
          }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className="num-tabular font-semibold leading-none tracking-tight"
          style={{ fontSize: size * 0.3, color: ring }}
        >
          {clamped}
        </span>
        <span className="mt-1 text-[10px] font-medium tracking-[0.22em] text-ink-subtle">
          {t("ring.label")}
        </span>
        <span className="mt-0.5 text-[11px] font-semibold" style={{ color: ring }}>
          {t(BAND_LABEL_KEYS[scoreBand(clamped)])}
        </span>
      </div>
    </div>
  );
}
