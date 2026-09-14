"use client";

/** Ordered list of deep per-turn cards (transcript order when ledger present). */

import { useT } from "@/i18n";
import type { TurnNote } from "@/types/domains/report";
import type { LedgerDocument } from "@/types/domains/records";
import { DeepQaCard } from "./DeepQaCard";

/** Sort notes into ledger turn order; unknown turns keep relative order. */
export function orderNotesByLedger(
  notes: TurnNote[],
  ledger: LedgerDocument | null,
): TurnNote[] {
  if (!ledger?.turns?.length) return notes;
  const order = new Map<string, number>();
  ledger.turns.forEach((turn, i) => {
    if (turn.turn_id) order.set(turn.turn_id, i);
  });
  return [...notes].sort(
    (a, b) => (order.get(a.turn_id) ?? 1 << 30) - (order.get(b.turn_id) ?? 1 << 30),
  );
}

export function TurnDeepNotes({
  notes,
  ledger,
}: {
  notes?: TurnNote[];
  ledger: LedgerDocument | null;
}) {
  const t = useT("report");
  if (!notes?.length) return null;
  const ordered = orderNotesByLedger(notes, ledger);
  return (
    <section className="eval-section">
      <h3 className="eval-label">{t("tabs.turns")}</h3>
      <ul className="space-y-3">
        {ordered.map((note) => (
          <DeepQaCard key={note.turn_id} note={note} />
        ))}
      </ul>
    </section>
  );
}
