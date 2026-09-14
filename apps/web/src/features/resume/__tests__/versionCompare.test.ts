/**
 * @file versionCompare.test.ts
 * @description Family grouping, scored series, and dimension deltas.
 */

import { describe, expect, it } from "vitest";

import type { ResumeResponse } from "@/lib/api/contract";
import { normalizeResume } from "../resumeNormalize";
import { makeResumeResponse } from "./helpers";
import {
  dimensionDeltas,
  familyIdOf,
  familyScoreSeries,
  familyScoredVersions,
  groupResumeFamilies,
  isLatestIdle,
  overlayRadarSeries,
  previousScorePoint,
  previousScoredVersion,
} from "../versionCompare";

function row(overrides: Partial<ResumeResponse> = {}) {
  return normalizeResume(makeResumeResponse(overrides));
}

const dims = {
  a: { score: 60, comment: "" },
  b: { score: 70, comment: "" },
  c: { score: 80, comment: "" },
  d: { score: 50, comment: "" },
};

describe("versionCompare", () => {
  it("treats missing family_id as the row id", () => {
    expect(familyIdOf({ id: 9 })).toBe(9);
    expect(familyIdOf({ id: 9, family_id: 0 })).toBe(9);
    expect(familyIdOf({ id: 9, family_id: 3 })).toBe(3);
  });

  it("groups by family and sorts members by version", () => {
    const v1 = row({
      id: 1,
      family_id: 1,
      version_n: 1,
      created_at: "2026-01-01T00:00:00Z",
    });
    const v2 = row({
      id: 2,
      family_id: 1,
      version_n: 2,
      created_at: "2026-01-02T00:00:00Z",
    });
    const other = row({
      id: 3,
      family_id: 3,
      version_n: 1,
      created_at: "2026-01-03T00:00:00Z",
    });
    const groups = groupResumeFamilies([v1, other, v2]);
    expect(groups.map((g) => g.familyId)).toEqual([3, 1]);
    expect(groups[1]?.members.map((m) => m.id)).toEqual([1, 2]);
  });

  it("builds scored series and deltas only for complete dimension maps", () => {
    const v1 = row({
      id: 1,
      family_id: 1,
      version_n: 1,
      score: 70,
      analysis: { score: 70, dimension_scores: dims },
    });
    const v2 = row({
      id: 2,
      family_id: 1,
      version_n: 2,
      score: 82,
      analysis: {
        score: 82,
        dimension_scores: {
          a: { score: 72, comment: "" },
          b: { score: 70, comment: "" },
          c: { score: 90, comment: "" },
          d: { score: 50, comment: "" },
        },
      },
    });
    const versions = familyScoredVersions([v1, v2], 1);
    expect(versions.map((item) => item.version_n)).toEqual([1, 2]);
    expect(previousScoredVersion(versions, 2)?.id).toBe(1);
    const deltas = dimensionDeltas(versions[1]!, versions[0]!, ["a", "b", "c", "missing"]);
    expect(deltas.find((d) => d.key === "a")?.delta).toBe(12);
    expect(deltas.find((d) => d.key === "b")?.delta).toBe(0);
    expect(deltas.find((d) => d.key === "c")?.delta).toBe(10);
    expect(deltas.find((d) => d.key === "missing")).toBeUndefined();
  });

  it("does not build overlay polygons when the current row is not scored", () => {
    const v1 = row({
      id: 1,
      family_id: 1,
      version_n: 1,
      score: 70,
      analysis: { score: 70, dimension_scores: dims },
    });
    const v2 = row({
      id: 2,
      family_id: 1,
      version_n: 2,
      score: 82,
      analysis: { score: 82, dimension_scores: dims },
    });
    const versions = familyScoredVersions([v1, v2], 1);
    expect(overlayRadarSeries(versions, 99, ["a", "b", "c", "d"])).toEqual([]);
    expect(overlayRadarSeries(versions, 2, ["a", "b", "c", "d"]).length).toBe(1);
  });

  it("keeps dims-less scored rows in the score series for the compare view", () => {
    // v1 is an older run: scored overall but without dimension detail.
    const v1 = row({ id: 1, family_id: 1, version_n: 1, score: 68, analysis: { score: 68 } });
    const v2 = row({
      id: 2,
      family_id: 1,
      version_n: 2,
      score: 77,
      analysis: { score: 77, dimension_scores: dims },
    });
    const series = familyScoreSeries([v1, v2], 1);
    expect(series.map((p) => p.version_n)).toEqual([1, 2]);
    expect(series[0]?.dimensions).toBeNull();
    expect(series[1]?.dimensions).not.toBeNull();
    const prev = previousScorePoint(series, 2);
    expect(prev?.id).toBe(1);
    expect(prev?.dimensions).toBeNull();
  });

  it("marks the newest idle version in a multi-version family", () => {
    const v1 = row({ id: 1, family_id: 1, version_n: 1, is_active: true });
    const v2 = row({ id: 2, family_id: 1, version_n: 2, is_active: false });
    const group = groupResumeFamilies([v1, v2])[0]!;
    expect(isLatestIdle(group, v2)).toBe(true);
    expect(isLatestIdle(group, v1)).toBe(false);
  });
});
