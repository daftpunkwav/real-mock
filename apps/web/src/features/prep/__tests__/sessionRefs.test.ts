/** sessionRefs: hash detection, stripping, candidate filtering. */

import { describe, expect, it } from "vitest";

import type { PrepSessionSummary } from "@/lib/api/contract";
import { detectHashQuery, refCandidates, refLabel, stripHashQuery } from "../sessionRefs";

function session(partial: Partial<PrepSessionSummary> & { id: number }): PrepSessionSummary {
  return {
    resume_id: null,
    resume_filename: null,
    summary: "",
    message_count: 0,
    status: "active",
    linked_session_id: null,
    token_usage: 0,
    prompt_tokens: 0,
    completion_tokens: 0,
    cached_tokens: 0,
    created_at: "",
    updated_at: "",
    ...partial,
  };
}

describe("detectHashQuery", () => {
  it("detects a trailing hash token", () => {
    expect(detectHashQuery("#")).toEqual({ query: "" });
    expect(detectHashQuery("hello #abc")).toEqual({ query: "abc" });
    expect(detectHashQuery("no token")).toBeNull();
    expect(detectHashQuery("#a #b")).toEqual({ query: "b" });
    expect(detectHashQuery("#ab cd")).toBeNull();
  });
});

describe("stripHashQuery", () => {
  it("removes the trailing token", () => {
    expect(stripHashQuery("#abc")).toBe("");
    expect(stripHashQuery("hello #abc")).toBe("hello");
  });
});

describe("refLabel", () => {
  it("prefers summary, then filename, then fallback", () => {
    expect(refLabel({ summary: "S", resume_filename: "F" }, "N")).toBe("S");
    expect(refLabel({ summary: "", resume_filename: "F" }, "N")).toBe("F");
    expect(refLabel({ summary: "", resume_filename: "" }, "N")).toBe("N");
  });
});

describe("refCandidates", () => {
  const list = [
    session({ id: 1, summary: "Backend prep" }),
    session({ id: 2, summary: "Frontend mock" }),
    session({ id: 3, summary: "", resume_filename: "r.pdf" }),
  ];

  it("excludes current and picked sessions, filters by query", () => {
    expect(refCandidates(list, 1, [], "", "N").map((c) => c.id)).toEqual([2, 3]);
    expect(refCandidates(list, null, [2], "", "N").map((c) => c.id)).toEqual([1, 3]);
    expect(refCandidates(list, null, [], "front", "N").map((c) => c.id)).toEqual([2]);
    expect(refCandidates(list, null, [], "zzz", "N")).toEqual([]);
  });
});
