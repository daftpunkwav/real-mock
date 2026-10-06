/**
 * @file sendToPrep.test.ts
 * @description Deep-link builder/parser contract between the deep-review sheet
 * and the prep page (resume pairing + seeded question round-trip).
 */

import { describe, expect, it } from "vitest";

import { buildPrepDeepLink, parsePrepDeepLink } from "../sendToPrep";

describe("buildPrepDeepLink", () => {
  it("carries the resume id and the encoded question", () => {
    const link = buildPrepDeepLink(7, "介绍一下 Agent Loop");
    expect(link.startsWith("/prep?")).toBe(true);
    const parsed = parsePrepDeepLink(link.slice("/prep".length));
    expect(parsed).toEqual({ resumeId: 7, question: "介绍一下 Agent Loop" });
  });

  it("omits the resume param when pairing is unknown", () => {
    const link = buildPrepDeepLink(null, "question");
    expect(link).toBe("/prep?q=question");
    expect(parsePrepDeepLink("?q=question")).toEqual({ resumeId: null, question: "question" });
  });
});

describe("parsePrepDeepLink", () => {
  it("returns null when no question is present", () => {
    expect(parsePrepDeepLink("")).toBeNull();
    expect(parsePrepDeepLink("?resume=3")).toBeNull();
    expect(parsePrepDeepLink("?q=%20%20")).toBeNull();
  });

  it("accepts only numeric resume ids", () => {
    expect(parsePrepDeepLink("?resume=abc&q=x")).toEqual({ resumeId: null, question: "x" });
    expect(parsePrepDeepLink("?resume=12&q=x")).toEqual({ resumeId: 12, question: "x" });
  });

  it("preserves newlines in the seeded question", () => {
    const question = "标题\n\n正文";
    const parsed = parsePrepDeepLink(`?q=${encodeURIComponent(question)}`);
    expect(parsed?.question).toBe(question);
  });
});
