"use client";

/** One deep per-turn analysis card: question, intent, your answer, score,
 * problems, reference answer (collapsible), how to answer, knowledge points,
 * knowledge brush-up, practice drills. */

import { useState } from "react";
import { useT } from "@/i18n";
import { ChevronDown } from "lucide-react";
import { tokenizeEvalText } from "@/lib/cnText";
import type { TurnNote } from "@/types/domains/report";

function scoreTone(score: number | undefined): string {
  const s = score ?? 0;
  if (s >= 80) return "chip-green";
  if (s >= 60) return "chip-yellow";
  if (s > 0) return "chip-red";
  return "chip-gray";
}

/** Render **bold** / `code` spans in agent prose (same tokenizer as resume eval). */
export function ReportRichText({ text }: { text: string }) {
  const parts = tokenizeEvalText(text);
  return (
    <>
      {parts.map((p, i) =>
        p.type === "bold" ? (
          <strong key={i} className="eval-em">
            {p.value}
          </strong>
        ) : p.type === "code" ? (
          <code key={i} className="eval-code">
            {p.value}
          </code>
        ) : (
          <span key={i}>{p.value}</span>
        ),
      )}
    </>
  );
}

export function DeepQaCard({ note, index }: { note: TurnNote; index?: number }) {
  const t = useT("report");
  // Weak answers auto-expand the reference so the miss is visible immediately;
  // strong answers keep it collapsible to reduce noise.
  const weak = (note.score ?? 0) > 0 && (note.score ?? 0) < 60;
  const [showReference, setShowReference] = useState(weak);
  const hasLegacy =
    Boolean(note.user_review?.summary) || Boolean(note.interviewer_review?.intent);
  const hasDeep =
    Boolean(note.question || note.reference_answer || note.how_to_answer ||
      (note.problems ?? []).length > 0 || (note.knowledge_points ?? []).length > 0 ||
      note.knowledge_brushup || (note.exercises ?? []).length > 0);

  return (
    <li className="eval-qa-card">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2">
          {typeof index === "number" && (
            <span className="eval-qa-idx num-tabular">{index + 1}</span>
          )}
          <div className="min-w-0">
            {note.question ? (
              <p className="text-[13px] font-semibold leading-relaxed text-ink">
                <ReportRichText text={note.question} />
              </p>
            ) : (
              <p className="text-[11px] font-semibold text-ink-subtle">{note.turn_id}</p>
            )}
            {note.question_intent && (
              <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">
                {t("qa.intent")}: <ReportRichText text={note.question_intent} />
              </p>
            )}
          </div>
        </div>
        {(note.score ?? 0) > 0 && (
          <span className={`chip shrink-0 ${scoreTone(note.score)} num-tabular`}>
            {note.score}
          </span>
        )}
      </div>

      {note.answer_summary && (
        <p className="mt-2 text-[13px] leading-relaxed text-ink-muted">
          <ReportRichText text={note.answer_summary} />
        </p>
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
                <span>
                  <ReportRichText text={p} />
                </span>
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
              <ReportRichText text={note.reference_answer} />
            </div>
          )}
        </div>
      )}

      {note.how_to_answer && (
        <p className="mt-2.5 text-[12px] leading-relaxed text-ink">
          <span className="font-medium text-[var(--info-ink)]">{t("qa.howToAnswer")}: </span>
          <ReportRichText text={note.how_to_answer} />
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

      {note.knowledge_brushup && (
        <p className="mt-2.5 text-[12px] leading-relaxed text-ink">
          <span className="font-medium text-[var(--info-ink)]">{t("qa.brushup")}: </span>
          <ReportRichText text={note.knowledge_brushup} />
        </p>
      )}

      {(note.exercises ?? []).length > 0 && (
        <div className="mt-2.5">
          <p className="mb-1 text-[10px] uppercase tracking-[0.08em] text-[var(--info-ink)]">
            {t("qa.exercises")}
          </p>
          <ol className="list-decimal space-y-1 pl-4">
            {(note.exercises ?? []).map((e, i) => (
              <li key={i} className="text-[12px] leading-relaxed text-ink">
                <ReportRichText text={e} />
              </li>
            ))}
          </ol>
        </div>
      )}

      {note.followup_quality && (
        <p className="mt-2 text-[11px] text-ink-muted">
          {t("qa.followup")}: <ReportRichText text={note.followup_quality} />
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
