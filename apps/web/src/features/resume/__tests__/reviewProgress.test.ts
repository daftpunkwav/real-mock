import { describe, expect, it } from "vitest";

import { applyAnalyzeEvent, type ReviewLiveState } from "../reviewProgress";

const empty: ReviewLiveState = { steps: [], timeline: [] };

describe("applyAnalyzeEvent", () => {
  it("keeps plan steps and folds consecutive thinking into one row", () => {
    const withPlan = applyAnalyzeEvent(empty, {
      type: "plan",
      steps: [{ id: "1", title: "Read resume", status: "in_progress" }],
    });
    const first = applyAnalyzeEvent(withPlan, { type: "thinking", content: "Look at" }, 1_000);
    const second = applyAnalyzeEvent(first, { type: "thinking", content: " projects" }, 1_200);
    expect(second.steps).toHaveLength(1);
    expect(second.timeline).toHaveLength(1);
    expect(second.timeline[0]).toMatchObject({
      kind: "thinking",
      content: "Look at projects",
      startedAt: 1_000,
    });
  });

  it("closes thinking when a tool starts and updates the same tool id", () => {
    let state = applyAnalyzeEvent(empty, { type: "thinking", content: "Plan first" }, 1_000);
    state = applyAnalyzeEvent(
      state,
      {
        type: "tool_step",
        id: "tool-1",
        name: "web_search",
        query: "agent engineer",
        status: "running",
        args: { query: "agent engineer" },
      },
      2_000,
    );
    state = applyAnalyzeEvent(
      state,
      {
        type: "tool_step",
        id: "tool-1",
        name: "web_search",
        query: "agent engineer",
        status: "done",
        result: '{"hit_count":1}',
        sites: ["zhipin.com", "linkedin.com"],
      },
      3_000,
    );
    expect(state.timeline).toHaveLength(2);
    expect(state.timeline[0]).toMatchObject({ kind: "thinking", endedAt: 2_000 });
    expect(state.timeline[1]).toMatchObject({
      kind: "tool",
      id: "tool-1",
      name: "web_search",
      status: "done",
      sites: ["zhipin.com", "linkedin.com"],
    });
  });

  it("ignores plan-bookkeeping tools so they do not split thinking", () => {
    let state = applyAnalyzeEvent(empty, { type: "thinking", content: "Inspect" }, 1_000);
    state = applyAnalyzeEvent(
      state,
      { type: "tool_step", id: "tool-p", name: "review_set_plan", status: "done" },
      1_500,
    );
    state = applyAnalyzeEvent(state, { type: "thinking", content: " more" }, 1_600);
    expect(state.timeline).toHaveLength(1);
    expect(state.timeline[0]).toMatchObject({ kind: "thinking", content: "Inspect more" });
  });

  it("keeps later thinking after a tool as a new row", () => {
    let state = applyAnalyzeEvent(
      empty,
      { type: "tool_step", id: "tool-1", name: "resume_get_section", status: "done" },
      1,
    );
    state = applyAnalyzeEvent(state, { type: "thinking", content: "Now score" }, 2);
    expect(state.timeline.map((item) => item.kind)).toEqual(["tool", "thinking"]);
  });

  it("strips leading blank lines from a new thinking row", () => {
    const afterTool = applyAnalyzeEvent(
      empty,
      { type: "tool_step", id: "tool-1", name: "web_search", status: "done" },
      1,
    );
    const state = applyAnalyzeEvent(
      afterTool,
      { type: "thinking", content: "\n\nNow I have a picture" },
      2,
    );
    expect(state.timeline[1]).toMatchObject({
      kind: "thinking",
      content: "Now I have a picture",
    });
  });

  it("ignores whitespace-only thinking chunks", () => {
    const state = applyAnalyzeEvent(empty, { type: "thinking", content: "\n\n  " }, 1);
    expect(state.timeline).toHaveLength(0);
  });

  it("appends notice events and closes open thinking first", () => {
    let state = applyAnalyzeEvent(empty, { type: "thinking", content: "Reading" }, 1_000);
    state = applyAnalyzeEvent(
      state,
      { type: "notice", kind: "vision_unavailable", message: "text-only review" },
      2_000,
    );
    expect(state.timeline).toHaveLength(2);
    expect(state.timeline[0]).toMatchObject({ kind: "thinking", endedAt: 2_000 });
    expect(state.timeline[1]).toMatchObject({ kind: "notice", content: "text-only review" });
  });

  it("ignores empty notice messages", () => {
    const state = applyAnalyzeEvent(empty, { type: "notice", message: "  " }, 1);
    expect(state.timeline).toHaveLength(0);
  });
});
