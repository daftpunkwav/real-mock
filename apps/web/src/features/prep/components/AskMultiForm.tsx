"use client";

/**
 * @file AskMultiForm.tsx
 * @description Multi-question ask form: one section per question (options,
 * slider, rating, optional per-question custom input when allow_custom),
 * answered and submitted as a whole. Pure presentational; answer state lives
 * in the owning modal.
 */

import { Check, Star } from "lucide-react";
import { useT } from "@/i18n";
import type { AskUserDialog } from "@/types";
import { formatSliderValue } from "@/lib/askDialog";

/** One question's pending answer inside a multi-question form. */
export interface MultiAnswer {
  custom?: string;
  picked?: string[];
  slider?: string;
  rating?: number;
}

export function MultiQuestionForm({
  questions,
  answers,
  disabled,
  onPatch,
}: {
  questions: AskUserDialog[];
  answers: Record<number, MultiAnswer>;
  disabled?: boolean;
  onPatch: (idx: number, patch: MultiAnswer) => void;
}) {
  const t = useT("prep");
  return (
    <>
      {questions.map((q, idx) => {
        const a = answers[idx] ?? {};
        const qMax = Math.min(10, Math.max(3, Math.round(q.scale?.max ?? 5)));
        const qMin = q.scale?.min ?? 0;
        const qMaxRange = q.scale?.max ?? 10;
        const qStep = q.scale?.step && q.scale.step > 0 ? q.scale.step : 1;
        return (
          <div key={idx} className="space-y-2">
            <p className="text-[13px] font-medium leading-relaxed text-ink">
              <span className="mr-1.5 text-ink-subtle">{idx + 1}.</span>
              {q.question}
            </p>
            {q.widget === "slider" && (
              <div>
                <div className="flex items-baseline justify-between">
                  <span className="text-[11px] text-ink-subtle">{qMin}</span>
                  <span className="text-[16px] font-semibold text-ink">
                    {formatSliderValue(a.slider ?? String(qMin), q.scale?.unit ?? "")}
                  </span>
                  <span className="text-[11px] text-ink-subtle">{qMaxRange}</span>
                </div>
                <input
                  type="range"
                  className="mt-1 w-full"
                  min={qMin}
                  max={qMaxRange}
                  step={qStep}
                  value={a.slider ?? String(qMin)}
                  disabled={disabled}
                  onChange={(e) => onPatch(idx, { slider: e.target.value })}
                  aria-label={q.question}
                />
              </div>
            )}
            {q.widget === "rating" && (
              <div className="flex items-center gap-1.5">
                {Array.from({ length: qMax }, (_, i) => i + 1).map((star) => (
                  <button
                    key={star}
                    type="button"
                    disabled={disabled}
                    onClick={() => onPatch(idx, { rating: star })}
                    aria-label={`${q.question} ${star}/${qMax}`}
                    className={`rounded p-1 transition-transform hover:scale-110 disabled:cursor-not-allowed disabled:opacity-50 ${
                      (a.rating ?? 0) >= star ? "text-[var(--warning)]" : "text-ink-subtle"
                    }`}
                  >
                    <Star size={22} fill="currentColor" strokeWidth={0} />
                  </button>
                ))}
              </div>
            )}
            {q.widget === "options" &&
              (q.selection === "multi" ? (
                <div className="space-y-1.5">
                  {q.options.map((opt) => {
                    const on = (a.picked ?? []).includes(opt);
                    return (
                      <button
                        key={opt}
                        type="button"
                        disabled={disabled}
                        onClick={() =>
                          onPatch(idx, {
                            picked: on
                              ? (a.picked ?? []).filter((o) => o !== opt)
                              : [...(a.picked ?? []), opt],
                          })
                        }
                        aria-pressed={on}
                        className="flex w-full items-center gap-2.5 rounded-md border border-surface-border bg-surface-alt px-3 py-2 text-left text-[13px] text-ink transition-colors hover:border-[var(--primary)] disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <span
                          className={`flex h-[16px] w-[16px] shrink-0 items-center justify-center rounded-[4px] border transition-colors ${
                            on
                              ? "border-[var(--primary)] bg-[var(--primary)] text-white"
                              : "border-ink-subtle text-transparent"
                          }`}
                        >
                          <Check size={12} strokeWidth={3} />
                        </span>
                        <span className="min-w-0 flex-1">{opt}</span>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div className="space-y-1.5">
                  {q.options.map((opt) => {
                    const on = (a.picked ?? [])[0] === opt;
                    return (
                      <button
                        key={opt}
                        type="button"
                        disabled={disabled}
                        onClick={() => onPatch(idx, { picked: [opt] })}
                        aria-pressed={on}
                        className={`flex w-full items-center gap-2.5 rounded-md border px-3 py-2 text-left text-[13px] text-ink transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                          on
                            ? "border-[var(--primary)] bg-[var(--info-soft)]"
                            : "border-surface-border bg-surface-alt hover:border-[var(--primary)]"
                        }`}
                      >
                        <span
                          className={`h-[14px] w-[14px] shrink-0 rounded-full border-2 ${
                            on ? "border-[var(--primary)] bg-[var(--primary)]" : "border-ink-subtle"
                          }`}
                        />
                        <span className="min-w-0 flex-1">{opt}</span>
                        {q.widget === "options" && q.suggested !== null && opt === q.suggested && (
                          <span className="ml-auto shrink-0 rounded-full bg-[var(--primary)] px-2 py-0.5 text-[10px] font-medium text-white">
                            {t("ask.recommended")}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              ))}
            {q.allow_custom && (
              <input
                className="field-input w-full"
                value={a.custom ?? ""}
                onChange={(e) => onPatch(idx, { custom: e.target.value })}
                placeholder={t("ask.customPlaceholder")}
                disabled={disabled}
                aria-label={q.question}
              />
            )}
          </div>
        );
      })}
    </>
  );
}
