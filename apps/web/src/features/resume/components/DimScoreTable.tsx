"use client";

/**
 * @file DimScoreTable.tsx
 * @description Compact dimension score table under the radar: name, score, colored band chip.
 */

import { useT } from "@/i18n";
import type { RadarDim } from "../analysisFormat";
import { bandColor, scoreBand } from "../analysisFormat";

export function DimScoreTable({
  dims,
  weights,
}: {
  dims: RadarDim[];
  /** Applied per-dimension weights (model-adjusted); omitted for legacy payloads. */
  weights?: Record<string, number>;
}) {
  const t = useT("resume");
  if (dims.length === 0) return null;
  const total = dims.reduce((sum, dim) => sum + (Number(weights?.[dim.key]) || 0), 0);
  const weightShare = (key: string): string => {
    const w = Number(weights?.[key]);
    if (!Number.isFinite(w) || w <= 0 || total <= 0) return "—";
    return `${Math.round((w / total) * 100)}%`;
  };
  return (
    <div>
      <p className="eval-label !mb-2">{t("overview.dimTable")}</p>
      <table className="eval-dim-table">
        <thead>
          <tr>
            <th>{t("overview.dimName")}</th>
            <th className="num-tabular">{t("overview.dimScore")}</th>
            <th>{t("overview.dimBand")}</th>
            {weights ? <th className="num-tabular">{t("overview.dimWeight")}</th> : null}
          </tr>
        </thead>
        <tbody>
          {dims.map((dim) => {
            const band = scoreBand(dim.score);
            return (
              <tr key={dim.key}>
                <td>{dim.label}</td>
                <td className="num-tabular">{dim.score}</td>
                <td>
                  <span
                    className="eval-band-chip"
                    style={{ color: bandColor(band) }}
                  >
                    {t(`overview.band.${band}`)}
                  </span>
                </td>
                {weights ? <td className="num-tabular">{weightShare(dim.key)}</td> : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
