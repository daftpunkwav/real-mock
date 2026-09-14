/**
 * @file resumeLimits
 * @description Single frontend catalog for resume upload, analyze, and UI caps.
 *
 * Responsibilities:
 * - Declare extensions, byte/parallel caps, dimension keys, preview/zoom numbers
 * - Derive the file-input accept string
 *
 * Aligned with openapi ResumeDomainLimits via contractLimits.test.ts.
 * Does not import React, HTTP, or i18n.
 */

export const RESUME_UPLOAD_EXTENSIONS = ["pdf", "docx", "md", "txt"] as const;

export const RESUME_ACCEPT = RESUME_UPLOAD_EXTENSIONS.map((ext) => `.${ext}`).join(",");

export const RESUME_MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

export const MAX_PARALLEL_ANALYZE = 3;

export const FILENAME_MAX_LENGTH = 255;

export const FILE_TYPE_MAX_LENGTH = 20;

export const ANALYSIS_LOCALES = ["zh-CN", "en"] as const;

export const DIMENSION_KEYS = [
  "structure_clarity",
  "visual_layout",
  "typography",
  "impact_quantification",
  "tech_depth",
  "project_narrative",
  "role_fit",
  "keyword_ats",
  "credibility",
  "seniority_signal",
  "growth_signal",
  "collaboration_signal",
] as const;

export type DimensionKey = (typeof DIMENSION_KEYS)[number];

export const TRUST_KEYS = ["solid", "claimed", "missing"] as const;

export type TrustKey = (typeof TRUST_KEYS)[number];

export const PREVIEW_SKILL_MAX = 12;

export const PREVIEW_SKILL_CHARS = 24;

export const PREVIEW_PROJECT_MAX = 3;

export const PREVIEW_MIN_ZOOM = 0.5;

export const PREVIEW_MAX_ZOOM = 4;

export const PREVIEW_ZOOM_STEP = 1.2;

/** Aligned with api `SCORE_BAND_*` via OpenAPI catalog (contractLimits.test.ts). */
export const SCORE_BAND_FAIR = 55;
export const SCORE_BAND_STRONG = 70;
export const SCORE_BAND_STANDOUT = 85;

export const MAX_RESUME_VERSIONS = 6;

export const PERCENTILE_FLOOR = 8;
export const PERCENTILE_CEILING = 92;

/** Persist-time floor; aligned with api `MIN_SCORED_DIMENSIONS` via OpenAPI catalog. */
export const MIN_SCORED_DIMENSIONS = 4;

/** Clamp a preview zoom factor to the catalog min/max. */
export function clampPreviewZoom(
  z: number,
  min = PREVIEW_MIN_ZOOM,
  max = PREVIEW_MAX_ZOOM,
): number {
  return Math.min(max, Math.max(min, z));
}
