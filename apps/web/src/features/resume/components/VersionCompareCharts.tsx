"use client";

/**
 * @file VersionCompareCharts.tsx
 * @description Score sparkline across the family plus dimension deltas vs the previous version.
 *
 * The score series accepts rows without dimension detail (older runs); when the
 * previous row lacks dimensions only the overall delta is shown.
 */

import { useT } from "@/i18n";
import type { RadarDim } from "../analysisFormat";
import {
  dimensionDeltas,
  familyScoreSeries,
  familyIdOf,
  previousScorePoint,
} from "../versionCompare";
import type { ResumeItem } from "../resumeNormalize";

/** Plot geometry for the score sparkline (axis gutter on the left). */
const PLOT = { w: 280, h: 88, gutter: 30, padRight: 12, top: 12, bottom: 22 };

function scoreScale(scores: number[]): {
  x: (i: number) => number;
  y: (score: number) => number;
  ticks: number[];
  line: string;
} {
  // Dynamic bounds with headroom so realistic score steps stay visible; clamped to 0-100.
  const lo = Math.max(0, Math.min(...scores) - 8);
  const hi = Math.min(100, Math.max(...scores) + 8);
  const span = Math.max(1, hi - lo);
  const { w, h, gutter, padRight, top, bottom } = PLOT;
  const x = (i: number) =>
    gutter + (i * (w - gutter - padRight)) / Math.max(1, scores.length - 1);
  const y = (score: number) =>
    top + (1 - (score - lo) / span) * (h - top - bottom);
  const ticks = [lo, Math.round((lo + hi) / 2), hi].filter(
    (v, i, arr) => arr.indexOf(v) === i,
  );
  const line = scores
    .map((score, i) => `${x(i).toFixed(1)},${y(score).toFixed(1)}`)
    .join(" ");
  return { x, y, ticks, line };
}

export function VersionCompareCharts({
  familyRows = [],
  currentId,
  radarDims,
}: {
  familyRows?: ResumeItem[];
  currentId: number;
  radarDims: RadarDim[];
}) {
  const t = useT("resume");
  const currentRow = familyRows.find((row) => row.id === currentId);
  const series =
    currentRow != null ? familyScoreSeries(familyRows, familyIdOf(currentRow)) : [];
  if (series.length < 2) return null;
  const current = series.find((row) => row.id === currentId);
  if (current == null) return null;
  const previous = previousScorePoint(series, current.id);

  const { x, y, ticks, line } = scoreScale(series.map((row) => row.score));
  const dimsReady = current.dimensions != null && previous?.dimensions != null;
  const keys = radarDims.map((dim) => dim.key);
  const deltas =
    dimsReady && current.dimensions && previous?.dimensions
      ? dimensionDeltas(
          { ...current, dimensions: current.dimensions },
          { ...previous, dimensions: previous.dimensions },
          keys,
        )
      : [];
  const maxAbs = Math.max(1, ...deltas.map((row) => Math.abs(row.delta)));
  const scoreDelta = previous ? current.score - previous.score : null;

  return (
    <div className="eval-compare">
      <p className="eval-label !mb-2">{t("overview.compareTitle")}</p>
      <div>
        <p className="mb-1 text-[11px] text-ink-subtle">{t("overview.compareScores")}</p>
        <svg viewBox="0 0 280 88" role="img" aria-label={t("overview.compareScores")}>
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={PLOT.gutter}
                x2={PLOT.w - PLOT.padRight}
                y1={y(tick)}
                y2={y(tick)}
                stroke="var(--border)"
                strokeDasharray="3 3"
              />
              <text
                x={PLOT.gutter - 6}
                y={y(tick) + 3}
                textAnchor="end"
                fontSize={8}
                fill="var(--muted-foreground)"
              >
                {tick}
              </text>
            </g>
          ))}
          <polyline
            points={line}
            fill="none"
            stroke="var(--primary)"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          {series.map((row, i) => (
            <g key={row.id}>
              <circle cx={x(i)} cy={y(row.score)} r={row.id === currentId ? 4 : 3} fill="var(--primary)" />
              <text
                x={x(i)}
                y={y(row.score) - 8}
                textAnchor="middle"
                fontSize={9}
                fill="var(--foreground)"
              >
                {row.score}
              </text>
              <text
                x={x(i)}
                y={PLOT.h - 6}
                textAnchor="middle"
                fontSize={9}
                fill="var(--muted-foreground)"
              >
                v{row.version_n}
              </text>
            </g>
          ))}
        </svg>
      </div>

      {previous ? (
        <p className="text-[11px] text-ink-muted">
          {t("overview.compareOverall", {
            prev: previous.score,
            curr: current.score,
            delta: scoreDelta ?? 0,
          })}
        </p>
      ) : null}

      {deltas.length > 0 ? (
        <div>
          <p className="mb-1.5 text-[11px] text-ink-subtle">{t("overview.compareDeltas")}</p>
          <div className="space-y-1">
            {deltas.map((row) => {
              const dim = radarDims.find((item) => item.key === row.key);
              const width = `${(Math.abs(row.delta) / maxAbs) * 100}%`;
              const up = row.delta >= 0;
              return (
                <div key={row.key} className="eval-delta-row">
                  <span className="truncate text-ink-muted">{dim?.label ?? row.key}</span>
                  <span className="num-tabular text-right text-ink">
                    {up ? "+" : ""}
                    {row.delta}
                  </span>
                  <div className="eval-delta-bar">
                    <span
                      style={{
                        width,
                        background: up ? "var(--success)" : "var(--danger)",
                        marginLeft: up ? 0 : "auto",
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : previous && !dimsReady ? (
        <p className="text-[11px] text-ink-subtle">{t("overview.compareDimsMissing")}</p>
      ) : null}
    </div>
  );
}
