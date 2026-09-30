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
import { resolvePhaseLabels } from "@/config/phases";
import type { TurnNote } from "@/types/domains/report";
import type { LedgerDocument } from "@/types/domains/records";
import { groupNotesByPhase } from "../turnGroups";
import { DeepQaCard } from "./DeepQaCard";

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
