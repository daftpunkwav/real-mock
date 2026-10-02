/**
 * Pure grouping logic for the report deep-dive: ledger ordering plus phase
 * grouping against the phase SSOT. No React, so tests can import it without
 * pulling in the component tree.
 */

import { PHASE_ORDER } from "@/config/phases";
import type { TurnNote } from "@/types/domains/report";
import type { LedgerDocument } from "@/types/domains/records";

/** Sort notes into ledger turn order; unknown turns keep relative order. */
export function orderNotesByLedger(notes: TurnNote[], ledger: LedgerDocument | null): TurnNote[] {
  if (!ledger?.turns?.length) return notes;
  const order = new Map<string, number>();
  ledger.turns.forEach((turn, i) => {
    if (turn.turn_id) order.set(turn.turn_id, i);
  });
  return [...notes].sort(
    (a, b) => (order.get(a.turn_id) ?? 1 << 30) - (order.get(b.turn_id) ?? 1 << 30),
  );
}

export interface TurnPhaseGroup {
  /** Phase id; "" marks the trailing group of phase-less notes. */
  phase: string;
  /** Display name: localized SSOT label, raw id for unknown phases, "" for ungrouped. */
  label: string;
  notes: TurnNote[];
}

const PHASE_RANK = new Map(PHASE_ORDER.map((id, i) => [id, i]));

/**
 * Group ledger-ordered notes by phase. Ranking: SSOT phase order first,
 * unknown phases after it in first-appearance order (stable sort keeps the
 * Map's insertion order within the tied rank), phase-less notes last.
 */
export function groupNotesByPhase(
  notes: TurnNote[],
  ledger: LedgerDocument | null,
  labels: Record<string, string>,
): TurnPhaseGroup[] {
  const ordered = orderNotesByLedger(notes, ledger);
  const buckets = new Map<string, TurnNote[]>();
  for (const note of ordered) {
    const phase = note.phase?.trim() || "";
    const bucket = buckets.get(phase);
    if (bucket) bucket.push(note);
    else buckets.set(phase, [note]);
  }
  const rank = (phase: string) =>
    PHASE_RANK.get(phase) ?? (phase ? PHASE_ORDER.length : PHASE_ORDER.length + 1);
  return [...buckets.entries()]
    .sort((a, b) => rank(a[0]) - rank(b[0]))
    .map(([phase, groupNotes]) => ({
      phase,
      label: phase ? (labels[phase] ?? phase) : "",
      notes: groupNotes,
    }));
}
