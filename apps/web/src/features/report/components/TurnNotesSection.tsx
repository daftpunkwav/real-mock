/**
 * Per-turn debrief notes: user review + interviewer review.
 */

"use client";

import { useT } from "@/i18n";
import type { TurnNote } from "@/types/domains/report";

/** Renders turn_notes from the debrief report payload. */
export function TurnNotesSection({ notes }: { notes?: TurnNote[] }) {
  const t = useT("report");
  if (!notes?.length) return null;

  return (
    <section className="mt-4 rounded-md border border-surface-border bg-surface-card p-4">
      <h2 className="mb-3 text-[13px] font-semibold tracking-tight text-ink">{t("turns.notesTitle")}</h2>
      <ul className="space-y-3">
        {notes.map((note) => {
          const user = note.user_review;
          const interviewer = note.interviewer_review;
          return (
            <li
              key={note.turn_id}
              className="rounded-md border border-surface-border bg-surface-alt p-3"
            >
              <p className="mb-2 text-[11px] font-semibold text-ink">{note.turn_id}</p>

              {(user?.summary || (user?.suggestions && user.suggestions.length > 0)) && (
                <div className="mb-2">
                  <p className="mb-1 text-[10px] uppercase tracking-[0.08em] text-ink-subtle">
                    {t("turns.candidatePerformance")}
                  </p>
                  {user?.summary && (
                    <p className="text-[13px] leading-relaxed text-ink">{user.summary}</p>
                  )}
                  {user?.suggestions && user.suggestions.length > 0 && (
                    <ul className="mt-1.5 space-y-1">
                      {user.suggestions.map((s, i) => (
                        <li key={i} className="flex items-start gap-2 text-[12px] text-ink-muted">
                          <span className="mt-1.5 inline-block h-1 w-1 shrink-0 rounded-full bg-current opacity-50" />
                          <span>{s}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {(interviewer?.intent || interviewer?.quality || interviewer?.notes) && (
                <div>
                  <p className="mb-1 text-[10px] uppercase tracking-[0.08em] text-ink-subtle">
                    {t("turns.interviewerReview")}
                  </p>
                  {interviewer?.intent && (
                    <p className="text-[12px] text-ink-muted">
                      <span className="font-medium text-ink">{t("turns.intentLabel")}</span>
                      {interviewer.intent}
                    </p>
                  )}
                  {interviewer?.quality && (
                    <p className="text-[12px] text-ink-muted">
                      <span className="font-medium text-ink">{t("turns.qualityLabel")}</span>
                      {interviewer.quality}
                    </p>
                  )}
                  {interviewer?.notes && (
                    <p className="mt-1 text-[13px] leading-relaxed text-ink">{interviewer.notes}</p>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
