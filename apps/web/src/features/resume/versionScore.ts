/**
 * @file versionScore.ts
 * @description Pure helpers for score series, dimension deltas, and radar overlays.
 *
 * Two series shapes: ``ScoredVersion`` (complete dimension map, radar overlays)
 * and ``ScorePoint`` (overall score only, version-compare view).
 *
 * Must not import React, HTTP, or i18n.
 */

import { dimScore } from "./analysisFormat";
import { MIN_SCORED_DIMENSIONS } from "./resumeLimits";
import type { ResumeItem } from "./resumeNormalize";
import { familyIdOf } from "./versionFamily";

export type ScoredVersion = {
  id: number;
  version_n: number;
  score: number;
  dimensions: Record<string, number>;
};

export type ScorePoint = {
  id: number;
  version_n: number;
  score: number;
  /** Full dimension map when present; older rows may only carry the overall score. */
  dimensions: Record<string, number> | null;
};

export type DimensionDelta = {
  key: string;
  previous: number;
  current: number;
  delta: number;
};

function dimensionMap(analysis: Record<string, unknown> | undefined): Record<string, number> {
  const raw = analysis?.dimension_scores;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const out: Record<string, number> = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    out[key] = dimScore(value as never);
  }
  return out;
}

function overallScore(row: ResumeItem, analysis: Record<string, unknown> | undefined): number | null {
  if (typeof row.score === "number") return row.score;
  if (typeof analysis?.score === "number") return Number(analysis.score);
  return null;
}

function versionNumber(row: ResumeItem): number {
  return Math.max(1, Number(row.version_n) || 1);
}

export function scoredVersionOf(row: ResumeItem): ScoredVersion | null {
  const analysis = row.analysis as Record<string, unknown> | undefined;
  const dimensions = dimensionMap(analysis);
  if (Object.keys(dimensions).length < MIN_SCORED_DIMENSIONS) return null;
  const score = overallScore(row, analysis);
  if (score == null) return null;
  return {
    id: row.id,
    version_n: versionNumber(row),
    score,
    dimensions,
  };
}

export function familyScoredVersions(rows: ResumeItem[], familyId: number): ScoredVersion[] {
  return rows
    .filter((row) => familyIdOf(row) === familyId)
    .map(scoredVersionOf)
    .filter((row): row is ScoredVersion => row != null)
    .sort((a, b) => a.version_n - b.version_n);
}

/** Score-series point: only the overall score is required, dimensions optional. */
export function scorePointOf(row: ResumeItem): ScorePoint | null {
  const analysis = row.analysis as Record<string, unknown> | undefined;
  const dims = dimensionMap(analysis);
  const hasDims = Object.keys(dims).length >= MIN_SCORED_DIMENSIONS;
  const score = overallScore(row, analysis);
  if (score == null) return null;
  return {
    id: row.id,
    version_n: versionNumber(row),
    score,
    dimensions: hasDims ? dims : null,
  };
}

/** All scored rows of a family by version, including rows without dimension detail. */
export function familyScoreSeries(rows: ResumeItem[], familyId: number): ScorePoint[] {
  return rows
    .filter((row) => familyIdOf(row) === familyId)
    .map(scorePointOf)
    .filter((row): row is ScorePoint => row != null)
    .sort((a, b) => a.version_n - b.version_n);
}

export function previousScorePoint(
  series: ScorePoint[],
  currentId: number,
): ScorePoint | null {
  const index = series.findIndex((row) => row.id === currentId);
  if (index <= 0) return null;
  return series[index - 1] ?? null;
}

export function previousScoredVersion(
  versions: ScoredVersion[],
  currentId: number,
): ScoredVersion | null {
  const index = versions.findIndex((row) => row.id === currentId);
  if (index <= 0) return null;
  return versions[index - 1] ?? null;
}

export function dimensionDeltas(
  current: ScoredVersion,
  previous: ScoredVersion,
  keys: string[],
): DimensionDelta[] {
  const out: DimensionDelta[] = [];
  for (const key of keys) {
    const cur = current.dimensions[key];
    const prev = previous.dimensions[key];
    if (cur == null || prev == null) continue;
    out.push({ key, previous: prev, current: cur, delta: cur - prev });
  }
  return out;
}

/** Earlier scored versions as radar polygons. Empty when ``currentId`` is not scored. */
export function overlayRadarSeries(
  versions: ScoredVersion[],
  currentId: number,
  keys: string[],
  maxOverlays = 2,
): number[][] {
  if (!versions.some((row) => row.id === currentId)) return [];
  return versions
    .filter((row) => row.id !== currentId)
    .slice(-maxOverlays)
    .map((row) => keys.map((key) => Number(row.dimensions[key] ?? 0)));
}
