/**
 * @file versionCompare.ts
 * @description Compatibility facade: family helpers live in versionFamily.ts,
 * score helpers live in versionScore.ts. Existing components and tests keep
 * importing from here.
 */

export {
  canAddVersion,
  familyIdOf,
  groupResumeFamilies,
  isLatestIdle,
  type ResumeFamilyGroup,
} from "./versionFamily";
export {
  dimensionDeltas,
  type DimensionDelta,
  familyScoreSeries,
  familyScoredVersions,
  overlayRadarSeries,
  previousScorePoint,
  previousScoredVersion,
  type ScoredVersion,
  scorePointOf,
  type ScorePoint,
  scoredVersionOf,
} from "./versionScore";
