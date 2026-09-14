"use client";

/**
 * @file OverviewTab.tsx
 * @description Analysis overview: narrative, role fit, radar, tables, notes,
 * version compare, percentile.
 */

import type { ResumeAnalysis } from "../types";
import type { ResumeItem } from "../resumeNormalize";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { useT } from "@/i18n";
import { EvalRichText } from "./EvalRichText";
import { RadarChart } from "./RadarChart";
import { DimScoreTable } from "./DimScoreTable";
import { VersionCompareCharts } from "./VersionCompareCharts";
import { InterviewerNotes, PercentileBar } from "./ImpressionCards";
import type { RadarDim } from "../analysisFormat";
import { familyIdOf, familyScoredVersions, overlayRadarSeries } from "../versionCompare";

export function OverviewTab({
  analysis,
  radarDims,
  percentile,
  familyRows = [],
  currentId,
}: {
  analysis: ResumeAnalysis;
  radarDims: RadarDim[];
  percentile: number | null;
  familyRows?: ResumeItem[];
  currentId?: number;
}) {
  const t = useT("resume");
  const cn = normalizeCnPunctuation;
  const currentRow =
    currentId != null ? familyRows.find((row) => row.id === currentId) : undefined;
  const scoredVersions =
    currentRow != null ? familyScoredVersions(familyRows, familyIdOf(currentRow)) : [];
  const overlayKeys = radarDims.map((dim) => dim.key);
  const overlays =
    currentId != null ? overlayRadarSeries(scoredVersions, currentId, overlayKeys) : [];

  return (
    <>
      {(analysis.overall_narrative || analysis.role_fit_summary) && (
        <div className="eval-overview-split">
          {analysis.overall_narrative ? (
            <section className="eval-section">
              <span className="eval-label">{t("overview.narrative")}</span>
              <p className="eval-prose eval-prose-fill">
                <EvalRichText text={cn(analysis.overall_narrative)} />
              </p>
            </section>
          ) : null}
          {analysis.role_fit_summary ? (
            <section className="eval-callout">
              <span className="eval-label">{t("overview.roleFit")}</span>
              <p className="eval-prose eval-prose-sm eval-prose-fill">
                <EvalRichText text={cn(analysis.role_fit_summary)} />
              </p>
            </section>
          ) : null}
        </div>
      )}

      {radarDims.length >= 3 && (
        <section className="eval-section">
          <span className="eval-label">{t("overview.radar")}</span>
          <div className="eval-radar-grid">
            <div className="eval-radar-sticky">
              <RadarChart dims={radarDims} overlays={overlays} />
              <DimScoreTable dims={radarDims} weights={analysis.dimension_weights} />
              {currentId != null ? (
                <VersionCompareCharts
                  familyRows={familyRows}
                  currentId={currentId}
                  radarDims={radarDims}
                />
              ) : null}
            </div>
            <div className="eval-dim-grid eval-dim-grid-compact">
              {radarDims.map((d) => (
                <div key={d.key} className="min-w-0">
                  <div className="flex items-baseline justify-between gap-3 mb-1.5">
                    <span className="eval-dim-name">{d.label}</span>
                    <span className="eval-dim-score">{d.score}</span>
                  </div>
                  <div className="progress !h-1">
                    <div
                      className="progress-bar"
                      style={{ width: `${Math.min(d.score, 100)}%` }}
                    />
                  </div>
                  {d.comment ? (
                    <p className="eval-dim-comment">
                      <EvalRichText text={cn(d.comment)} />
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {percentile != null && <PercentileBar pct={percentile} />}

      {analysis.interviewer_comments && analysis.interviewer_comments.length > 0 && (
        <InterviewerNotes items={analysis.interviewer_comments} />
      )}
    </>
  );
}
