/** groupNotesByPhase: ledger ordering + phase grouping for the deep-dive pager. */

import { describe, expect, it } from "vitest";
import { groupNotesByPhase, orderNotesByLedger } from "../turnGroups";
import { PHASE_ORDER } from "@/config/phases";
import type { TurnNote } from "@/types/domains/report";
import type { LedgerDocument } from "@/types/domains/records";

function note(turnId: string, phase?: string): TurnNote {
  return { turn_id: turnId, ...(phase ? { phase } : {}) };
}

function ledger(turnIds: string[]): LedgerDocument {
  return {
    turns: turnIds.map((turn_id) => ({ turn_id })),
  } as LedgerDocument;
}

const LABELS: Record<string, string> = {
  self_intro: "自我介绍",
  basic_knowledge: "基础知识",
  project_deep_dive: "项目深挖",
};

describe("groupNotesByPhase", () => {
  it("orders groups by the phase SSOT and numbers notes inside each group", () => {
    const groups = groupNotesByPhase(
      [
        note("t1", "project_deep_dive"),
        note("t2", "self_intro"),
        note("t3", "basic_knowledge"),
        note("t4", "self_intro"),
      ],
      null,
      LABELS,
    );
    expect(groups.map((g) => g.phase)).toEqual([
      "self_intro",
      "basic_knowledge",
      "project_deep_dive",
    ]);
    expect(groups[0]!.notes.map((n) => n.turn_id)).toEqual(["t2", "t4"]);
    expect(groups[0]!.label).toBe("自我介绍");
  });

  it("places unknown phases after SSOT ones in first-appearance order", () => {
    const groups = groupNotesByPhase(
      [
        note("t1", "custom_round"),
        note("t2", "summary"),
        note("t3", "another_custom"),
        note("t4", "custom_round"),
      ],
      null,
      LABELS,
    );
    expect(groups.map((g) => g.phase)).toEqual(["summary", "custom_round", "another_custom"]);
    // Unknown ids fall back to the raw phase string as label.
    expect(groups[1]!.label).toBe("custom_round");
  });

  it("keeps phase-less notes in a trailing ungrouped group", () => {
    const groups = groupNotesByPhase(
      [note("t1"), note("t2", "self_intro"), note("t3", "  ")],
      null,
      LABELS,
    );
    expect(groups.map((g) => g.phase)).toEqual(["self_intro", ""]);
    expect(groups[1]!.label).toBe("");
    expect(groups[1]!.notes.map((n) => n.turn_id)).toEqual(["t1", "t3"]);
  });

  it("sorts inside groups by ledger turn order; ungrouped still trails", () => {
    const led = ledger(["t4", "t3", "t2", "t1"]);
    const groups = groupNotesByPhase(
      [note("t1", "self_intro"), note("t2", "self_intro"), note("t3"), note("t4")],
      led,
      LABELS,
    );
    // Ledger order governs within a group; the ungrouped bucket stays last.
    expect(groups.map((g) => g.phase)).toEqual(["self_intro", ""]);
    expect(groups[0]!.notes.map((n) => n.turn_id)).toEqual(["t2", "t1"]);
    expect(groups[1]!.notes.map((n) => n.turn_id)).toEqual(["t4", "t3"]);
  });

  it("never ranks a known phase below unknown or ungrouped ones", () => {
    const last = PHASE_ORDER[PHASE_ORDER.length - 1]!;
    const groups = groupNotesByPhase(
      [note("t1", last), note("t2", "zzz_unknown"), note("t3")],
      null,
      LABELS,
    );
    expect(groups.map((g) => g.phase)).toEqual([last, "zzz_unknown", ""]);
  });

  it("orders by ledger through orderNotesByLedger independently of phases", () => {
    const ordered = orderNotesByLedger([note("a"), note("b"), note("c")], ledger(["c", "a"]));
    expect(ordered.map((n) => n.turn_id)).toEqual(["c", "a", "b"]);
    expect(orderNotesByLedger([note("a")], null).map((n) => n.turn_id)).toEqual(["a"]);
  });
});
