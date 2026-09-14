"use client";

import { useT } from "@/i18n";
import type { NormalizedScores } from "../scoreFormat";

/** Lightweight report radar; resume RadarChart stays separate. */
export function ScoreRadar({ scores }: { scores: NormalizedScores }) {
  const t = useT("report");
  const dims = [
    { key: "technical" as const, labelKey: "radar.technical" },
    { key: "communication" as const, labelKey: "radar.communication" },
    { key: "project_depth" as const, labelKey: "radar.projectDepth" },
    { key: "problem_solving" as const, labelKey: "radar.problemSolving" },
    { key: "presence" as const, labelKey: "radar.presence" },
    { key: "politeness" as const, labelKey: "radar.politeness" },
  ];
  const cx = 120;
  const cy = 120;
  const r = 80;
  const values = dims.map((d) => {
    const v = scores[d.key];
    return typeof v === "number" ? Math.min(1, Math.max(0, v / 100)) : 0;
  });
  const points = dims
    .map((_, i) => {
      const angle = (Math.PI * 2 * i) / dims.length - Math.PI / 2;
      const v = values[i] ?? 0;
      return `${cx + Math.cos(angle) * r * v},${cy + Math.sin(angle) * r * v}`;
    })
    .join(" ");
  const rings = [0.25, 0.5, 0.75, 1];
  const hasAny = values.some((v) => v > 0);

  return (
    <div className="surface-card mb-6 p-4">
      <h3 className="mb-1 text-center text-[14px] font-semibold tracking-tight text-ink">
        {t("radar.title")}
      </h3>
      <p className="mb-4 text-center text-[11px] text-ink-subtle">{t("radar.subtitle")}</p>
      <div className="flex justify-center">
        <svg width="240" height="240" viewBox="0 0 240 240" aria-label={t("radar.title")}>
          {rings.map((ring) => (
            <polygon
              key={ring}
              points={dims
                .map((_, i) => {
                  const angle = (Math.PI * 2 * i) / dims.length - Math.PI / 2;
                  return `${cx + Math.cos(angle) * r * ring},${cy + Math.sin(angle) * r * ring}`;
                })
                .join(" ")}
              fill="none"
              stroke="var(--border)"
              strokeWidth="1"
            />
          ))}
          {dims.map((d, i) => {
            const angle = (Math.PI * 2 * i) / dims.length - Math.PI / 2;
            const x = cx + Math.cos(angle) * (r + 18);
            const y = cy + Math.sin(angle) * (r + 18);
            const score = scores[d.key];
            return (
              <text
                key={d.key}
                x={x}
                y={y}
                textAnchor="middle"
                dominantBaseline="middle"
                className="fill-ink-subtle"
                style={{ fontSize: 10 }}
              >
                {t(d.labelKey)}
                {typeof score === "number" ? ` ${score}` : ""}
              </text>
            );
          })}
          {hasAny && (
            <polygon
              points={points}
              fill="color-mix(in srgb, var(--primary) 28%, transparent)"
              stroke="var(--primary)"
              strokeWidth="2"
            />
          )}
          {!hasAny && (
            <text
              x={cx}
              y={cy}
              textAnchor="middle"
              dominantBaseline="middle"
              className="fill-ink-subtle"
              style={{ fontSize: 11 }}
            >
              {t("radar.empty")}
            </text>
          )}
        </svg>
      </div>
    </div>
  );
}
