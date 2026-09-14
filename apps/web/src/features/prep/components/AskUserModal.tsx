"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, HelpCircle, Send, Star } from "lucide-react";
import { useT } from "@/i18n";
import type { AskUserDialog } from "@/types";
import { formatAskAnswer, formatSliderValue } from "@/lib/askDialog";
import { readAskTimeoutSec } from "@/lib/askTimeout";

interface AskUserModalProps {
  dialog: AskUserDialog;
  disabled?: boolean;
  onAnswer: (text: string) => void;
  onClose: () => void;
}

/** One question's pending answer inside a multi-question form. */
interface MultiAnswer {
  custom?: string;
  picked?: string[];
  slider?: string;
  rating?: number;
}

/**
 * @file AskUserModal.tsx
 * @description Agent question dialog. A dialog carries 1-8 questions: the flat
 * fields drive the single-question form (radio circles, checkbox squares,
 * numeric slider, star rating, always-on custom input, recommended-choice
 * auto-submit); a `questions` array renders one multi-question form answered
 * and submitted as a whole, each reply line formatted as "question: answer".
 * Answers are returned as plain text via onAnswer.
 */

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
    // A new dialog may arrive while the modal stays mounted: drop stale picks.
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
  const timeoutSec = useMemo(() => readAskTimeoutSec(), []);
  const deadline = useMemo(
    () => (timeoutSec > 0 && autoChoice ? Date.now() + timeoutSec * 1000 : null),
    [timeoutSec, autoChoice],
  );
  const [now, setNow] = useState(() => Date.now());
  const autoFiredRef = useRef(false);
  useEffect(() => {
    if (deadline === null) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [deadline]);
  const remainingMs = deadline === null ? null : Math.max(0, deadline - now);
  useEffect(() => {
    if (remainingMs === 0 && autoChoice && !autoFiredRef.current && !custom.trim()) {
      autoFiredRef.current = true;
      answer(autoChoice);
    }
  });

  const formatRemaining = (ms: number): string => {
    const total = Math.ceil(ms / 1000);
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
  };

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

  const multiQuestion = (q: AskUserDialog, idx: number) => {
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
              onChange={(e) => setAnswer(idx, { slider: e.target.value })}
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
                onClick={() => setAnswer(idx, { rating: star })}
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
                      setAnswer(idx, {
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
                    onClick={() => setAnswer(idx, { picked: [opt] })}
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
                    {q.widget === "options" && q.suggested !== null && opt === q.suggested && recommendBadge}
                  </button>
                );
              })}
            </div>
          ))}
        {q.allow_custom && (
          <input
            className="field-input w-full"
            value={a.custom ?? ""}
            onChange={(e) => setAnswer(idx, { custom: e.target.value })}
            placeholder={t("ask.customPlaceholder")}
            disabled={disabled}
            aria-label={q.question}
          />
        )}
      </div>
    );
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
            {multiQuestions.map((q, idx) => multiQuestion(q, idx))}
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
