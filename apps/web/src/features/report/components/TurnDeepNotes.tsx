"use client";

/**
 * Deep per-turn analysis, paginated by interview phase. Notes keep ledger
 * order inside each group; groups follow the phase SSOT order, then unknown
 * phases by first appearance, and phase-less notes land in a trailing
 * "ungrouped" bucket. The pager only renders with 2+ groups; inactive groups
 * stay mounted (hidden) so each card's fold state survives page switches.
 */

import { useMemo, useState } from "react";
import { useLocale, useT } from "@/i18n";
import { PHASE_ORDER, resolvePhaseLabels } from "@/config/phases";
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

export function TurnDeepNotes({
  notes,
  ledger,
}: {
  notes?: TurnNote[];
  ledger: LedgerDocument | null;
}) {
  const t = useT("report");
  const { locale } = useLocale();
  const labels = useMemo(() => resolvePhaseLabels(null, locale), [locale]);
  const groups = useMemo(
    () => (notes?.length ? groupNotesByPhase(notes, ledger, labels) : []),
    [notes, ledger, labels],
  );
  const [active, setActive] = useState<string | null>(null);
  if (!groups.length) return null;
  const currentPhase = groups.some((g) => g.phase === active)
    ? (active as string)
    : groups[0]!.phase;
  const paginated = groups.length > 1;
  return (
    <section className="eval-section">
      <h3 className="eval-label">{t("tabs.turns")}</h3>
      {paginated && (
        <div
          className="mb-4 flex flex-wrap gap-1.5"
          role="group"
          aria-label={t("turns.phaseTabsAria")}
        >
          {groups.map((g) => {
            const isActive = g.phase === currentPhase;
            return (
              <button
                key={g.phase || "ungrouped"}
                type="button"
                aria-pressed={isActive}
                onClick={() => setActive(g.phase)}
                className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[12px] transition-colors ${
                  isActive
                    ? "border-[var(--primary)] bg-[var(--info-soft)] font-medium text-ink"
                    : "border-surface-border text-ink-muted hover:border-[var(--primary)] hover:text-ink"
                }`}
              >
                {g.label || t("qa.ungrouped")}
                <span className="num-tabular text-[11px] text-ink-subtle">
                  {g.notes.length}
                </span>
              </button>
            );
          })}
        </div>
      )}
      {/* All groups stay mounted: hidden ones keep their DeepQaCard fold
          state and numbering restarts per phase page. */}
      {groups.map((g) => {
        const visible = !paginated || g.phase === currentPhase;
        return (
          <ul
            key={g.phase || "ungrouped"}
            className={`space-y-3 ${visible ? "" : "hidden"}`}
            aria-hidden={!visible}
          >
            {g.notes.map((note, i) => (
              <DeepQaCard key={note.turn_id} note={note} index={i} />
            ))}
          </ul>
        );
      })}
    </section>
  );
}
