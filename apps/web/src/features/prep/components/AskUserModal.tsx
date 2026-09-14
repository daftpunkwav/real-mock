"use client";

/**
 * @file AskUserModal.tsx
 * @description Agent question dialog. A dialog carries 1-8 questions: the flat
 * fields drive the single-question form (radio circles, checkbox squares,
 * numeric slider, star rating, optional custom input when allow_custom,
 * recommended-choice auto-submit); a `questions` array longer than one
 * renders one multi-question form answered and submitted as a whole, each
 * reply line formatted as "question: answer". Answers return as plain text
 * via onAnswer.
 */

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, HelpCircle, Send, Star } from "lucide-react";
import { useT } from "@/i18n";
import type { AskUserDialog } from "@/types";
import { formatAskAnswer, formatSliderValue } from "@/lib/askDialog";
import { useAskAutoSubmit } from "../hooks/useAskAutoSubmit";
import { MultiQuestionForm, type MultiAnswer } from "./AskMultiForm";

interface AskUserModalProps {
  dialog: AskUserDialog;
  disabled?: boolean;
  onAnswer: (text: string) => void;
  onClose: () => void;
}

export function AskUserModal({
  dialog,
  disabled = false,
  onAnswer,
  onClose,
}: AskUserModalProps) {
  const t = useT("prep");
  const { question, options, selection, widget, scale, allow_custom, suggested } = dialog;
  const multiQuestions = dialog.questions && dialog.questions.length > 1 ? dialog.questions : null;
  const isMulti = multiQuestions !== null;
  const [custom, setCustom] = useState("");
  const [checked, setChecked] = useState<string[]>([]);
  const [answers, setAnswers] = useState<Record<number, MultiAnswer>>({});
  const sliderMin = scale?.min ?? 0;
  const sliderMax = scale?.max ?? 10;
  const sliderStep = scale?.step && scale.step > 0 ? scale.step : 1;
  const [sliderValue, setSliderValue] = useState(String(sliderMin));
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // A new dialog may arrive while the modal stays mounted: drop stale picks
    // (the auto-submit guard re-arms inside useAskAutoSubmit).
    setCustom("");
    setChecked([]);
    setAnswers({});
    setSliderValue(String(sliderMin));
  }, [dialog, sliderMin]);

  useEffect(() => {
    // preventScroll: fixed overlay is already in view; plain focus() scrolls
    // a scrolled chat page toward the overlay's document slot.
    inputRef.current?.focus({ preventScroll: true });
  }, []);

  const anyTyping =
    custom.trim() !== "" ||
    Object.values(answers).some((a) => (a.custom ?? "").trim() !== "");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !anyTyping) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [anyTyping, onClose]);

  const answer = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onAnswer(trimmed);
  };

  // Auto-resolve: deadline-based so background tabs still expire on time.
  // Skipped while the user is composing custom text. Single-question dialogs
  // only: a multi-question form implies the user is present and answering.
  const autoChoice = !isMulti && suggested && !disabled ? suggested : null;
  const { remainingMs, formatRemaining } = useAskAutoSubmit(
    autoChoice,
    custom.trim() !== "",
    Boolean(disabled),
    answer,
  );

  const toggle = (opt: string) => {
    if (disabled) return;
    setChecked((prev) =>
      prev.includes(opt) ? prev.filter((o) => o !== opt) : [...prev, opt],
    );
  };

  const ratingMax = Math.min(10, Math.max(3, Math.round(scale?.max ?? 5)));

  const isRecommended = (opt: string) =>
    widget === "options" && suggested !== null && opt === suggested;

  const recommendBadge = (
    <span className="ml-auto shrink-0 rounded-full bg-[var(--primary)] px-2 py-0.5 text-[10px] font-medium text-white">
      {t("ask.recommended")}
    </span>
  );

  // ── Multi-question form ────────────────────────────────────────────────────

  const setAnswer = (idx: number, patch: MultiAnswer) =>
    setAnswers((prev) => ({ ...prev, [idx]: { ...prev[idx], ...patch } }));

  const multiAnswerText = (idx: number): string | null => {
    const q = multiQuestions?.[idx];
    if (!q) return null;
    const a = answers[idx] ?? {};
    const typed = a.custom?.trim();
    if (typed) return typed;
    if (q.widget === "slider") {
      return a.slider !== undefined
        ? formatSliderValue(a.slider, q.scale?.unit ?? "")
        : null;
    }
    if (q.widget === "rating") {
      return a.rating !== undefined ? formatAskAnswer(q, { rating: a.rating }) : null;
    }
    return a.picked && a.picked.length > 0 ? formatAskAnswer(q, { options: a.picked }) : null;
  };

  const submitMulti = () => {
    if (disabled) return;
    const lines = (multiQuestions ?? [])
      .map((q, idx) => ({ q, text: multiAnswerText(idx) }))
      .filter((x): x is { q: AskUserDialog; text: string } => x.text !== null)
      .map(({ q, text }) => `${q.question}: ${text}`);
    if (lines.length === 0) return;
    onAnswer(lines.join("\n"));
  };

  const renderBody = () => {
    if (widget === "slider") {
      return (
        <div className="mt-4">
          <div className="flex items-baseline justify-between">
            <span className="text-[11px] text-ink-subtle">{sliderMin}</span>
            <span className="text-[20px] font-semibold text-ink">
              {formatSliderValue(sliderValue, scale?.unit ?? "")}
            </span>
            <span className="text-[11px] text-ink-subtle">{sliderMax}</span>
          </div>
          <input
            type="range"
            className="mt-2 w-full"
            min={sliderMin}
            max={sliderMax}
            step={sliderStep}
            value={sliderValue}
            disabled={disabled}
            onChange={(e) => setSliderValue(e.target.value)}
            aria-label={question}
          />
          <button
            type="button"
            disabled={disabled}
            onClick={() => answer(formatAskAnswer(dialog, { slider: sliderValue }))}
            className="btn-primary mt-3 h-9 w-full"
          >
            {t("ask.confirm")}
          </button>
        </div>
      );
    }
    if (widget === "rating") {
      return (
        <div className="mt-4 flex items-center gap-1.5">
          {Array.from({ length: ratingMax }, (_, i) => i + 1).map((star) => (
            <button
              key={star}
              type="button"
              disabled={disabled}
              onClick={() => answer(formatAskAnswer(dialog, { rating: star }))}
              className="rounded p-1 text-[var(--warning)] transition-transform hover:scale-110 disabled:cursor-not-allowed disabled:opacity-50"
              aria-label={`${star}/${ratingMax}`}
            >
              <Star size={26} fill="currentColor" strokeWidth={0} />
            </button>
          ))}
        </div>
      );
    }
    if (selection === "multi") {
      return (
        <div className="mt-4 space-y-2">
          {options.map((opt) => {
            const on = checked.includes(opt);
            return (
              <button
                key={opt}
                type="button"
                disabled={disabled}
                onClick={() => toggle(opt)}
                aria-pressed={on}
                className="flex w-full items-center gap-2.5 rounded-md border border-surface-border bg-surface-alt px-3.5 py-2.5 text-left text-[13px] leading-relaxed text-ink transition-colors hover:border-[var(--primary)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <span
                  className={`flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[4px] border transition-colors ${
                    on
                      ? "border-[var(--primary)] bg-[var(--primary)] text-white"
                      : "border-ink-subtle text-transparent"
                  }`}
                >
                  <Check size={13} strokeWidth={3} />
                </span>
                <span className="min-w-0 flex-1">{opt}</span>
                {isRecommended(opt) && recommendBadge}
              </button>
            );
          })}
          <button
            type="button"
            disabled={disabled || checked.length === 0}
            onClick={() => answer(formatAskAnswer(dialog, { options: checked }))}
            className="btn-primary mt-1 h-9 w-full"
          >
            {t("ask.confirm")} ({checked.length})
          </button>
        </div>
      );
    }
    return (
      <div className="mt-4 space-y-2">
        {options.map((opt) => (
          <button
            key={opt}
            type="button"
            disabled={disabled}
            onClick={() => answer(opt)}
            className="flex w-full items-center gap-2.5 rounded-md border border-surface-border bg-surface-alt px-3.5 py-2.5 text-left text-[13px] leading-relaxed text-ink transition-colors hover:border-[var(--primary)] hover:bg-[var(--info-soft)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span className="h-[16px] w-[16px] shrink-0 rounded-full border-2 border-ink-subtle" />
            <span className="min-w-0 flex-1">{opt}</span>
            {isRecommended(opt) && recommendBadge}
          </button>
        ))}
      </div>
    );
  };

  // Portal out of the page tree: entrance animations above retain an identity
  // transform, which would otherwise contain this fixed overlay to a content
  // box instead of the viewport (partial dimming).
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 anim-fade-in"
      role="dialog"
      aria-modal="true"
      aria-label={multiQuestions ? multiQuestions.map((q) => q.question).join(" / ") : question}
    >
      <div className="surface-card max-h-[85vh] w-full max-w-md overflow-y-auto !p-5 anim-rise">
        <div className="flex items-start gap-3">
          <span className="icon-badge icon-badge-brand shrink-0">
            <HelpCircle size={16} />
          </span>
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--primary)]">
              {t("ask.title")}
            </p>
            {!isMulti && (
              <p className="mt-1 text-[14px] font-medium leading-relaxed text-ink">
                {question}
              </p>
            )}
            {!isMulti && widget === "options" && selection === "multi" && (
              <p className="mt-0.5 text-[11px] text-ink-subtle">{t("ask.multiHint")}</p>
            )}
            {remainingMs !== null && autoChoice && (
              <p className="mt-0.5 text-[11px] text-ink-subtle">
                {t("ask.autoIn", { time: formatRemaining(remainingMs), choice: autoChoice })}
              </p>
            )}
          </div>
        </div>

        {isMulti && multiQuestions ? (
          <div className="mt-4 space-y-5">
            <MultiQuestionForm questions={multiQuestions} answers={answers} disabled={disabled} onPatch={setAnswer} />
            <div>
              <p className="mb-2 text-center text-[11px] text-ink-subtle">
                {t("ask.progress", {
                  answered: multiQuestions.filter((_, i) => multiAnswerText(i) !== null).length,
                  total: multiQuestions.length,
                })}
              </p>
              <button
                type="button"
                disabled={disabled || multiQuestions.every((_, i) => multiAnswerText(i) === null)}
                onClick={submitMulti}
                className="btn-primary h-9 w-full"
              >
                {t("ask.confirm")}
              </button>
            </div>
          </div>
        ) : (
          <>
            {renderBody()}
            {allow_custom && (
              <div className="mt-4 flex gap-2">
                <input
                  ref={inputRef}
                  className="field-input flex-1"
                  value={custom}
                  onChange={(e) => setCustom(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && answer(custom)}
                  placeholder={t("ask.customPlaceholder")}
                  disabled={disabled}
                />
                <button
                  type="button"
                  onClick={() => answer(custom)}
                  disabled={disabled || !custom.trim()}
                  className="btn-primary !h-9 !w-11 shrink-0 !px-0"
                  aria-label={t("ask.send")}
                >
                  <Send size={14} />
                </button>
              </div>
            )}
          </>
        )}

        <button
          type="button"
          onClick={onClose}
          className="mt-3 w-full text-center text-[11px] text-ink-subtle transition-colors hover:text-ink-muted"
        >
          {t("ask.dismiss")}
        </button>
      </div>
    </div>,
    document.body,
  );
}
