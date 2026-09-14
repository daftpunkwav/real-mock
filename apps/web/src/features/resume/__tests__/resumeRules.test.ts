/**
 * @file resumeRules.test.ts
 * @description Pure resume helpers: normalize, selection, tabs, preview, analysis format, zoom.
 *
 * Also locks fixture override semantics (shallow replace) and abort-error detection.
 */

import { describe, expect, it } from "vitest";

import { asAnalysis, bandColor, dimComment, dimScore, percentileFromScore, scoreBand } from "../analysisFormat";
import { visibleAnalysisTabIds, TAB_LABEL_KEYS } from "../analysisTabs";
import { isRequestAborted } from "../isRequestAborted";
import { normalizeParsedProfile, normalizeResumeList } from "../resumeNormalize";
import { shortSkillLabel } from "../resumePreview";
import { pickPreviewId } from "../resumeSelection";
import { clampPreviewZoom, PREVIEW_MAX_ZOOM, PREVIEW_MIN_ZOOM } from "../resumeLimits";
import { ApiError } from "@/lib/api/base";
import type { CandidateProfile } from "@/lib/api/contract";

import { makeAnalysis, makeResumeResponse } from "./helpers";

describe("scoreBand and bandColor", () => {
  it("maps boundary scores to the API bands", () => {
    expect(scoreBand(85)).toBe("standout");
    expect(scoreBand(70)).toBe("solid");
    expect(scoreBand(55)).toBe("mixed");
    expect(scoreBand(54)).toBe("weak");
  });

  it("gives every band a distinct hue (dark-theme primary collides with danger)", () => {
    const hues = [bandColor("standout"), bandColor("solid"), bandColor("mixed"), bandColor("weak")];
    expect(new Set(hues).size).toBe(4);
    expect(hues).not.toContain("var(--primary)");
  });
});

describe("normalizeParsedProfile", () => {
  it("fills missing arrays", () => {
    // Cast: stored payloads from before the scalar fields existed stay sparse.
    const profile = normalizeParsedProfile({ name: "A", summary: "" } as CandidateProfile);
    expect(profile.skills).toEqual([]);
    expect(profile.projects).toEqual([]);
    expect(profile.name).toBe("A");
    expect(profile.parse_degraded).toBe(false);
  });

  it("treats null as empty", () => {
    expect(normalizeParsedProfile(null).name).toBe("");
  });
});

describe("normalizeResumeList", () => {
  it("maps rows and treats null as empty", () => {
    expect(normalizeResumeList(null)).toEqual([]);
    const list = normalizeResumeList([makeResumeResponse({ id: 9 })]);
    expect(list[0]?.id).toBe(9);
    expect(list[0]?.parsed_profile.skills).toEqual(["Python"]);
    expect(list[0]?.family_id).toBe(9);
    expect(list[0]?.version_n).toBe(1);
  });
});

describe("pickPreviewId", () => {
  const rows = [
    { id: 1, is_active: false },
    { id: 2, is_active: true },
    { id: 3, is_active: false },
  ];

  it("keeps the current id when still present", () => {
    expect(pickPreviewId(rows, 3)).toBe(3);
  });

  it("falls back to the active row, then the first row", () => {
    expect(pickPreviewId(rows, 99)).toBe(2);
    expect(pickPreviewId([{ id: 4 }, { id: 5 }], null)).toBe(4);
    expect(pickPreviewId([], 1)).toBeNull();
  });
});

describe("visibleAnalysisTabIds", () => {
  it("always includes overview", () => {
    expect(visibleAnalysisTabIds({ score: 10 } as never)).toEqual(["overview"]);
  });

  it("adds document / projects / interview / advice when those fields have content", () => {
    const tabs = visibleAnalysisTabIds({
      score: 10,
      project_cards: [{ name: "P", score: 1, one_line: "", highlights: [], risks: [], deep_questions: [] }],
      interview_qa: [{ question: "Q", intent: "", answer_points: [], follow_ups: [] }],
      skill_trust: { solid: ["Py"], claimed: [], missing: [] },
      layout_review: "cramped",
    } as never);
    expect(tabs).toEqual(["overview", "document", "projects", "interview", "advice"]);
  });

  it("treats rewrite_examples as advice and salary_positioning as career", () => {
    expect(
      visibleAnalysisTabIds({
        score: 1,
        rewrite_examples: [{ original: "a", rewritten: "b" }],
      } as never),
    ).toEqual(["overview", "advice"]);
    expect(
      visibleAnalysisTabIds({
        score: 1,
        salary_positioning: "median",
      } as never),
    ).toEqual(["overview", "career"]);
  });

  it("does not add empty project_cards as a projects tab", () => {
    expect(visibleAnalysisTabIds({ score: 1, project_cards: [] } as never)).toEqual(["overview"]);
  });

  it("TAB_LABEL_KEYS covers every visible tab id", () => {
    expect(Object.keys(TAB_LABEL_KEYS).sort()).toEqual(
      ["advice", "career", "document", "interview", "overview", "projects"].sort(),
    );
  });
});

describe("shortSkillLabel", () => {
  it("uses the first segment when it is a real label", () => {
    expect(shortSkillLabel("Python::advanced")).toBe("Python");
  });

  it("truncates long labels", () => {
    const long = "abcdefghijklmnopqrstuvwxyz";
    expect(shortSkillLabel(long, 8)).toBe("abcdefgh…");
  });

  it("keeps a one-character head instead of splitting", () => {
    expect(shortSkillLabel("")).toBe("");
    expect(shortSkillLabel("a:tail")).toBe("a:tail");
  });
});

describe("asAnalysis / dimScore / dimComment", () => {
  it("returns null without a score", () => {
    expect(asAnalysis(null)).toBeNull();
    expect(asAnalysis({})).toBeNull();
    expect(asAnalysis("x")).toBeNull();
    expect(asAnalysis({ score: 80 })?.score).toBe(80);
    expect(asAnalysis({ score: 0 })?.score).toBe(0);
  });

  it("returns null for non-numeric scores", () => {
    expect(asAnalysis({ score: "85" })).toBeNull();
    expect(asAnalysis({ score: null })).toBeNull();
    expect(asAnalysis({ score: undefined })).toBeNull();
  });

  it("reads numeric and object dimension values", () => {
    expect(dimScore(70)).toBe(70);
    expect(dimScore({ score: 40, comment: "ok" })).toBe(40);
    expect(dimScore({} as never)).toBe(0);
    expect(dimComment({ score: 40, comment: "  ok  " })).toBe("ok");
    expect(dimComment(12)).toBe("");
  });
});

describe("percentileFromScore", () => {
  it("maps 0/50/100 onto the 8–92 band", () => {
    expect(percentileFromScore(0)).toBe(8);
    expect(percentileFromScore(50)).toBe(50);
    expect(percentileFromScore(100)).toBe(92);
    expect(percentileFromScore(80)).toBe(75);
  });
});

describe("isRequestAborted", () => {
  it("detects NET0002 ApiError only", () => {
    expect(isRequestAborted(new ApiError("x", 0, { code: "NET0002" }))).toBe(true);
    expect(isRequestAborted(new ApiError("x", 0, { code: "NET0003" }))).toBe(false);
    expect(isRequestAborted(new Error("abort"))).toBe(false);
  });
});

describe("clampPreviewZoom", () => {
  it("clamps to catalog min/max", () => {
    expect(clampPreviewZoom(0)).toBe(PREVIEW_MIN_ZOOM);
    expect(clampPreviewZoom(99)).toBe(PREVIEW_MAX_ZOOM);
    expect(clampPreviewZoom(1.2)).toBe(1.2);
  });
});

describe("makeAnalysis fixture", () => {
  it("replaces nested objects instead of merging them", () => {
    const analysis = makeAnalysis({
      skill_trust: { solid: ["Go"], claimed: [], missing: [] },
    });
    expect(analysis.skill_trust?.solid).toEqual(["Go"]);
    expect(analysis.skill_trust?.missing).toEqual([]);
    expect(analysis.score).toBe(70);
  });
});
