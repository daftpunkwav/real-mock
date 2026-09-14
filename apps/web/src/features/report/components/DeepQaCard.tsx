"use client";

/** One deep per-turn analysis card: question, intent, your answer, score,
 * problems, reference answer (collapsible), how to answer, knowledge points. */

import { useState } from "react";
import { useT } from "@/i18n";
import { ChevronDown } from "lucide-react";
import type { TurnNote } from "@/types/domains/report";

function scoreTone(score: number | undefined): string {
  const s = score ?? 0;
  if (s >= 80) return "chip-green";
  if (s >= 60) return "chip-yellow";
  if (s > 0) return "chip-red";
  return "chip-gray";
}

export function DeepQaCard({ note }: { note: TurnNote }) {
  const t = useT("report");
  const [showReference, setShowReference] = useState(false);
  const hasLegacy =
    Boolean(note.user_review?.summary) || Boolean(note.interviewer_review?.intent);
  const hasDeep =
    Boolean(note.question || note.reference_answer || note.how_to_answer ||
      (note.problems ?? []).length > 0 || (note.knowledge_points ?? []).length > 0);

  return (
    <li className="eval-qa-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {note.question ? (
            <p className="text-[13px] font-semibold leading-relaxed text-ink">{note.question}</p>
          ) : (
            <p className="text-[11px] font-semibold text-ink-subtle">{note.turn_id}</p>
          )}
          {note.question_intent && (
            <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">
              {t("qa.intent")}: {note.question_intent}
            </p>
          )}
        </div>
        {(note.score ?? 0) > 0 && (
          <span className={`chip shrink-0 ${scoreTone(note.score)} num-tabular`}>
            {note.score}
          </span>
        )}
      </div>

      {note.answer_summary && (
        <p className="mt-2 text-[13px] leading-relaxed text-ink-muted">{note.answer_summary}</p>
      )}

      {(note.problems ?? []).length > 0 && (
        <div className="mt-2.5">
          <p className="mb-1 text-[10px] uppercase tracking-[0.08em] text-[var(--danger-ink)]">
            {t("qa.problems")}
          </p>
          <ul className="space-y-1">
            {(note.problems ?? []).map((p, i) => (
              <li key={i} className="flex items-start gap-2 text-[12px] leading-relaxed text-ink">
                <span className="mt-1.5 inline-block h-1 w-1 shrink-0 rounded-full bg-current opacity-50" />
                <span>{p}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {note.reference_answer && (
        <div className="mt-2.5">
          <button
            type="button"
            className="flex items-center gap-1 text-[11px] font-medium text-[var(--info-ink)]"
            onClick={() => setShowReference((v) => !v)}
          >
            {t("qa.reference")}
            <ChevronDown
              size={12}
              className={`transition-transform ${showReference ? "rotate-180" : ""}`}
            />
          </button>
          {showReference && (
            <div className="mt-1.5 rounded-md border border-surface-border bg-surface-alt p-2.5 text-[12px] leading-relaxed text-ink">
              {note.reference_answer}
            </div>
          )}
        </div>
      )}

      {note.how_to_answer && (
        <p className="mt-2.5 text-[12px] leading-relaxed text-ink">
          <span className="font-medium text-[var(--info-ink)]">{t("qa.howToAnswer")}: </span>
          {note.how_to_answer}
        </p>
      )}

      {(note.knowledge_points ?? []).length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1">
          {(note.knowledge_points ?? []).map((k, i) => (
            <span key={i} className="chip chip-gray !text-[10px]">
              {k}
            </span>
          ))}
        </div>
      )}

      {note.followup_quality && (
        <p className="mt-2 text-[11px] text-ink-muted">
          {t("qa.followup")}: {note.followup_quality}
        </p>
      )}

      {!hasDeep && hasLegacy && (
        <div className="mt-2 space-y-1.5">
          {note.user_review?.summary && (
            <p className="text-[13px] leading-relaxed text-ink">{note.user_review.summary}</p>
          )}
          {note.interviewer_review?.intent && (
            <p className="text-[12px] text-ink-muted">
              <span className="font-medium text-ink">{t("turns.intentLabel")}</span>
              {note.interviewer_review.intent}
            </p>
          )}
        </div>
      )}
    </li>
  );
}
