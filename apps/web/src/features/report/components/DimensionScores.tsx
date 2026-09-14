"use client";

import { useT } from "@/i18n";
import { formatScore, type NormalizedScores } from "../scoreFormat";
import { scoreColor } from "@/lib/scoreColor";

const DIMS = [
  { labelKey: "dimensions.technical", key: "technical" as const },
  { labelKey: "dimensions.communication", key: "communication" as const },
  { labelKey: "dimensions.projectDepth", key: "project_depth" as const },
  { labelKey: "dimensions.problemSolving", key: "problem_solving" as const },
  { labelKey: "dimensions.presence", key: "presence" as const },
  { labelKey: "dimensions.politeness", key: "politeness" as const },
];

/** Dimension score KPI grid. */
export function DimensionScores({ scores }: { scores: NormalizedScores }) {
  const t = useT("report");
  return (
    <div className="mb-6 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
      {DIMS.map((d) => {
        const value = scores[d.key];
        const display = formatScore(value);
        const numeric = typeof value === "number";
        return (
          <div
            key={d.key}
            className="kpi-card items-center text-center !p-3"
          >
            <div
              className="font-mono text-[24px] font-semibold leading-none num-tabular"
              style={{ color: numeric ? scoreColor(value) : undefined }}
            >
              {display}
            </div>
            <div className="kpi-label mt-2 text-center">{t(d.labelKey)}</div>
            {numeric && value != null && (
              <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-surface-muted">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${Math.min(100, Math.max(0, value))}%`,
                    backgroundColor: scoreColor(value),
                  }}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
