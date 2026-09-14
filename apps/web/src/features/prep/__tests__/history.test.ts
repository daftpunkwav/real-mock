/**
 * @file history.test.ts
 * @description Tests for prep history normalizers.
 */

import { describe, expect, it } from "vitest";

import {
  appendTraceThinking,
  appendTraceTool,
  buildTraceFromParts,
  mapHistoryMessages,
  normalizeSearchGroups,
  normalizeSteps,
  normalizeThinking,
} from "../history";

describe("normalizeSteps", () => {
  it("returns undefined for non-array input", () => {
    expect(normalizeSteps(undefined)).toBeUndefined();
    expect(normalizeSteps(null)).toBeUndefined();
    expect(normalizeSteps("x")).toBeUndefined();
  });

  it("fills missing query/result with empty strings", () => {
    const steps = normalizeSteps([
      { name: "web_search", query: "Note" },
      { name: "quiz" },
    ]);
    expect(steps).toEqual([
      { name: "web_search", query: "Note", result: "" },
      { name: "quiz", query: "", result: "" },
    ]);
  });

  it("drops entries without a name", () => {
    expect(normalizeSteps([{ query: "q" }, null, 42])).toBeUndefined();
  });
});

describe("normalizeSearchGroups", () => {
  it("returns undefined for non-array input", () => {
    expect(normalizeSearchGroups(undefined)).toBeUndefined();
    expect(normalizeSearchGroups({})).toBeUndefined();
  });

  it("keeps groups with query and results array", () => {
    const groups = normalizeSearchGroups([
      { query: "react interview tips", results: [{ url: "https://a.com" }] },
      { results: [] },
      { query: "no results" },
    ]);
    expect(groups).toEqual([{ query: "react interview tips", results: [{ url: "https://a.com" }] }]);
  });
});

describe("normalizeThinking", () => {
  it("rejects non-string input", () => {
    expect(normalizeThinking(123)).toBeUndefined();
    expect(normalizeThinking(null)).toBeUndefined();
  });

  it("trims text and drops blanks", () => {
    expect(normalizeThinking("   ")).toBeUndefined();
    expect(normalizeThinking("Note")).toBe("Note");
  });
});

describe("mapHistoryMessages", () => {
  const nextId = (prefix: string) => `${prefix}-1`;

  it("returns empty list for undefined input", () => {
    expect(mapHistoryMessages(undefined as never, nextId)).toEqual([]);
  });

  it("keeps user/assistant text and drops system/empty rows", () => {
    const mapped = mapHistoryMessages(
      [
        { role: "user", content: "Note" },
        { role: "assistant", content: "" },
        { role: "system", content: "sys" },
      ] as never,
      nextId,
    );
    expect(mapped).toHaveLength(1);
    expect(mapped[0]).toMatchObject({ role: "user", content: "Note" });
  });

  it("attaches steps, search groups, and thinking metadata", () => {
    const mapped = mapHistoryMessages(
      [
        {
          role: "assistant",
          content: "Note",
          steps: [{ name: "web_search", query: "system design basics" }],
          search_groups: [{ query: "system design basics", results: [] }],
          thinking: "Note",
        },
      ] as never,
      nextId,
    );
    expect(mapped[0]).toEqual({
      id: "a-1",
      role: "assistant",
      content: "Note",
      steps: [{ name: "web_search", query: "system design basics", result: "" }],
      searchGroups: [{ query: "system design basics", results: [] }],
      thinking: "Note",
      trace: [
        { kind: "thinking", text: "Note" },
        { kind: "tool", name: "web_search", query: "system design basics" },
      ],
      stopped: undefined,
      backendIndex: 0,
    });
  });

  it("attaches backend indices counting skipped entries, and stopped flags", () => {
    const mapped = mapHistoryMessages(
      [
        { role: "system", content: "sys" },
        { role: "user", content: "q" },
        { role: "assistant", content: "a", stopped: true },
      ] as never,
      nextId,
    );
    expect(mapped).toHaveLength(2);
    expect(mapped[0]).toMatchObject({ backendIndex: 1 });
    expect(mapped[1]).toMatchObject({ backendIndex: 2, stopped: true });
  });

  it("surfaces summary blocks as compaction cards with provenance", () => {
    const mapped = mapHistoryMessages(
      [
        { role: "user", content: "q" },
        {
          role: "system",
          content: "[Conversation Minutes] Session objectives: ship it\n[provenance v=2 backup_session=7 fork_point=4]",
        },
        { role: "assistant", content: "a" },
      ] as never,
      nextId,
    );
    expect(mapped).toHaveLength(3);
    // Cards sink below every message (creation order, not fold position).
    expect(mapped.map((m) => m.role)).toEqual(["user", "assistant", "compaction"]);
    const card = mapped[2]!;
    expect(card).toMatchObject({ content: "Session objectives: ship it", backendIndex: 1 });
    expect(card.compaction).toEqual({
      summary: "Session objectives: ship it",
      version: 2,
      forkPoint: 4,
      backupSessionId: 7,
      before: null,
      after: null,
    });
  });

  it("renders rule-fallback digests as read-only compaction cards", () => {
    const mapped = mapHistoryMessages(
      [{ role: "system", content: "[Context compression] Early 3 The dialogue has been omitted" }] as never,
      nextId,
    );
    expect(mapped).toHaveLength(1);
    expect(mapped[0]?.role).toBe("compaction");
    expect(mapped[0]?.compaction?.version).toBe(0);
  });

  it("keeps hiding non-summary system blocks", () => {
    const mapped = mapHistoryMessages(
      [
        { role: "system", content: "[Reply language] zh" },
        { role: "user", content: "q" },
      ] as never,
      nextId,
    );
    expect(mapped).toHaveLength(1);
    expect(mapped[0]?.role).toBe("user");
  });
});

describe("trace builders", () => {
  it("merges contiguous thinking deltas, splits on tool steps", () => {
    let trace = appendTraceThinking([], "think1 ");
    trace = appendTraceThinking(trace, "think2");
    trace = appendTraceTool(trace, { name: "web_search", query: "q" });
    trace = appendTraceThinking(trace, "more");
    expect(trace).toEqual([
      { kind: "thinking", text: "think1 think2" },
      { kind: "tool", name: "web_search", query: "q" },
      { kind: "thinking", text: "more" },
    ]);
  });

  it("buildTraceFromParts returns undefined when empty", () => {
    expect(buildTraceFromParts(undefined, undefined)).toBeUndefined();
  });

  it("carries tool args/result detail through the timeline", () => {
    const trace = appendTraceTool([], {
      name: "web_search",
      query: "q",
      args: { query: "q" },
      result: "obs",
    });
    expect(trace).toEqual([
      { kind: "tool", name: "web_search", query: "q", args: { query: "q" }, result: "obs" },
    ]);
    expect(
      buildTraceFromParts(undefined, [
        { name: "web_search", query: "q", args: { query: "q" }, result: "obs" },
      ]),
    ).toEqual(trace);
  });
});
