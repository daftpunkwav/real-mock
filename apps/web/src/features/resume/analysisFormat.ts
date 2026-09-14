/**
 * @file analysisFormat
 * @description Dimension labels and tolerant readers for untyped analysis JSON.
 *
 * Responsibilities:
 * - Map catalog dimension keys to i18n message keys
 * - Narrow list/detail `analysis` dicts into ResumeAnalysis when a score exists
 *
 * Must not import React. Labels live in the resume i18n namespace.
 */

import type { MessageKey } from "@/i18n";
import type { DimensionScore, ResumeAnalysis } from "@/lib/api/contract";
import { DIMENSION_KEYS, PERCENTILE_CEILING, PERCENTILE_FLOOR, SCORE_BAND_FAIR, SCORE_BAND_STANDOUT, SCORE_BAND_STRONG } from "./resumeLimits";

export const DIM_LABEL_KEYS: Record<string, MessageKey<"resume">> = Object.fromEntries(
  DIMENSION_KEYS.map((key) => [key, `dim.${key}` as MessageKey<"resume">]),
);

/** dimension_scores values may be a number (legacy) or `{ score, comment }`. */
type DimensionValue = DimensionScore | number;

export type { TabId } from "./analysisTabs";

export type DimEntry = [string, DimensionValue];

export interface RadarDim {
  key: string;
  label: string;
  score: number;
  comment: string;
}

/** Narrow a stored analysis dict; missing/non-numeric score → null (no fake review). */
export function asAnalysis(raw: unknown): ResumeAnalysis | null {
  if (!raw || typeof raw !== "object") return null;
  if (!("score" in raw)) return null;
  if (typeof (raw as { score?: unknown }).score !== "number") return null;
  return raw as ResumeAnalysis;
}

export function dimScore(v: DimensionValue): number {
  if (typeof v === "number") return v;
  if (v && typeof v === "object" && "score" in v) return Number((v as { score: number }).score) || 0;
  return 0;
}

export function dimComment(v: DimensionValue): string {
  if (v && typeof v === "object" && "comment" in v) {
    return String((v as { comment?: string }).comment || "").trim();
  }
  return "";
}

export type ScoreBandId = "weak" | "mixed" | "solid" | "standout";

/** Rubric bands shared with the API SCORE_BANDS catalog (85 / 70 / 55). */
export function scoreBand(score: number): ScoreBandId {
  const n = Number(score) || 0;
  if (n >= SCORE_BAND_STANDOUT) return "standout";
  if (n >= SCORE_BAND_STRONG) return "solid";
  if (n >= SCORE_BAND_FAIR) return "mixed";
  return "weak";
}

/**
 * Band chip color: one distinct hue per band.
 *
 * Never derive band colors from scoreColor(): in the dark theme
 * ``--primary`` (≈70–84 scores) is visually identical to ``--danger``.
 */
export function bandColor(band: ScoreBandId): string {
  switch (band) {
    case "standout":
      return "var(--success)";
    case "solid":
      return "var(--info)";
    case "mixed":
      return "var(--warning)";
    case "weak":
      return "var(--danger)";
  }
}

/** Same monotone map as the API: overall score → [8, 92], not a real peer sample. */
export function percentileFromScore(score: number): number {
  const clamped = Math.max(0, Math.min(100, Math.round(Number(score) || 0)));
  const span = PERCENTILE_CEILING - PERCENTILE_FLOOR;
  return PERCENTILE_FLOOR + Math.round((span * clamped) / 100);
}
