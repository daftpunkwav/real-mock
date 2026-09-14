/**
 * previewRoute unit tests: build/parse contract for preview-page query params.
 *
 * Covers:
 * - build → parse round-trip (including CJK filenames — encodeURIComponent)
 * - missing / illegal id fallbacks
 * - type suffix normalized to lowercase
 */

import { describe, expect, it } from "vitest";

import {
  buildResumePreviewUrl,
  parseResumePreviewParams,
  RESUME_PREVIEW_QUERY,
} from "../previewRoute";

describe("buildResumePreviewUrl", () => {
  it("builds a /resume/preview relative URL using contract query keys", () => {
    const url = buildResumePreviewUrl({ id: 3, name: "resume.pdf", type: "PDF" });
    expect(url.startsWith("/resume/preview?")).toBe(true);
    const parsed = parseResumePreviewParams(new URLSearchParams(url.split("?")[1]));
    expect(parsed).toEqual({ id: 3, name: "resume.pdf", type: "pdf" });
  });

  it("round-trips CJK filenames through URL encoding", () => {
    const url = buildResumePreviewUrl({ id: 42, name: "张三_简历.pdf", type: "pdf" });
    const parsed = parseResumePreviewParams(new URLSearchParams(url.split("?")[1]));
    expect(parsed.id).toBe(42);
    expect(parsed.name).toBe("张三_简历.pdf");
  });
});

describe("parseResumePreviewParams", () => {
  it("missing id → 0; missing name → injected fallback", () => {
    const parsed = parseResumePreviewParams(new URLSearchParams(), "Resume");
    expect(parsed.id).toBe(0);
    expect(parsed.name).toBe("Resume");
    expect(parsed.type).toBe("");
  });

  it("non-numeric id → 0", () => {
    const search = new URLSearchParams();
    search.set(RESUME_PREVIEW_QUERY.id, "abc");
    expect(parseResumePreviewParams(search).id).toBe(0);
  });

  it("normalizes type to lowercase", () => {
    const search = new URLSearchParams();
    search.set(RESUME_PREVIEW_QUERY.id, "1");
    search.set(RESUME_PREVIEW_QUERY.type, "PDF");
    expect(parseResumePreviewParams(search).type).toBe("pdf");
  });
});
