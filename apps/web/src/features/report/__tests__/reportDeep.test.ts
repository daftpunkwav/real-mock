/** Deep report tabs + live-event reducer + process eligibility helpers (pure logic). */

import { describe, expect, it } from "vitest";
import {
  REPORT_TAB_IDS,
  REPORT_TAB_LABEL_KEYS,
  defaultReportTab,
  visibleReportTabIds,
} from "../reportTabs";
import {
  REPORT_LIVE_MAX_EVENTS,
  applyReportLiveEvent,
  emptyReportLiveState,
} from "../liveEvents";
import {
  buildNextRoundIndex,
  selectEligibleProcesses,
} from "@/features/interview";
import type { DebriefReport } from "@/types/domains/report";
import type { InterviewProcessResponse } from "@/lib/api/contract";

function report(patch: Partial<DebriefReport> = {}): DebriefReport {
  return {
    overall_score: 80,
    score_breakdown: {} as DebriefReport["score_breakdown"],
    ...patch,
  } as DebriefReport;
}

describe("visibleReportTabIds", () => {
  it("always includes overview and adds tabs only when content exists", () => {
    const bare = visibleReportTabIds(report());
    expect(bare).toEqual(["overview"]);

    const full = visibleReportTabIds(
      report({
        turn_notes: [{ turn_id: "t1" }] as DebriefReport["turn_notes"] as DebriefReport["turn_notes"],
        verdict: "passed",
        highlights: ["x"],
        training_plan: ["y"],
      }),
    );
    expect(full).toEqual(["overview", "turns", "verdict", "plan"]);

    const failedOnly = visibleReportTabIds(report({ verdict: "failed", key_problems: ["p"] }));
    expect(failedOnly).toEqual(["overview", "verdict"]);
  });

  it("exposes a label key for every tab id (SSOT complete)", () => {
    for (const id of REPORT_TAB_IDS) {
      expect(REPORT_TAB_LABEL_KEYS[id]).toBeTruthy();
    }
    expect(defaultReportTab(report({ turn_notes: [{ turn_id: "t1" }] as DebriefReport["turn_notes"] }))).toBe("overview");
    expect(defaultReportTab(report())).toBe("overview");
  });
});

describe("applyReportLiveEvent", () => {
  it("keeps only progress event types", () => {
    let state = emptyReportLiveState();
    state = applyReportLiveEvent(state, { type: "token", content: "x" } as never);
    state = applyReportLiveEvent(state, { type: "done" } as never);
    expect(state.events).toEqual([]);
  });

  it("appends and caps at the configured size", () => {
    let state = emptyReportLiveState();
    for (let i = 0; i < REPORT_LIVE_MAX_EVENTS + 10; i++) {
      state = applyReportLiveEvent(state, { type: "tool_step", name: `t${i}` });
    }
    expect(state.events.length).toBe(REPORT_LIVE_MAX_EVENTS);
    expect(state.events.at(-1)?.name).toBe(`t${REPORT_LIVE_MAX_EVENTS + 9}`);
  });
});

describe("selectEligibleProcesses", () => {
  it("filters and normalizes next_round_no, newest first", () => {
    const proc = (id: number, eligible: boolean, next: number | null, created: string) =>
      ({
        id,
        next_round_eligible: eligible,
        next_round_no: next,
        created_at: created,
      }) as InterviewProcessResponse;

    const out = selectEligibleProcesses([
      proc(1, true, 2, "2026-09-01"),
      proc(2, false, null, "2026-09-02"),
      proc(3, true, 3, "2026-09-03"),
    ]);
    expect(out.map((p) => p.id)).toEqual([3, 1]);
    expect(out[0]?.next_round_no).toBe(3);
  });
});

describe("buildNextRoundIndex", () => {
  it("indexes eligible processes by id", () => {
    const proc = { id: 7, next_round_no: 2 } as InterviewProcessResponse & {
      next_round_no: number;
    };
    const index = buildNextRoundIndex([proc as never]);
    expect(index[7]?.next_round_no).toBe(2);
    expect(index[8]).toBeUndefined();
  });
});
