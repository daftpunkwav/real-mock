"use client";

/**
 * @file RateModal.tsx
 * @description Turn-rating dialog: 1–10 score, reason chips, free-form comment,
 * and memory tags. Submitted ratings are stored as long-term memories.
 */

import { useState } from "react";
import { createPortal } from "react-dom";
import { Plus, X } from "lucide-react";
import { useT, type MessageKey } from "@/i18n";
import { cn } from "@/lib/utils";

export interface RateSubmit {
  score: number;
  reasons: string[];
  comment: string;
  tags: string[];
}

/** Built-in reason chips; submitted values are the resolved labels. */
const REASON_KEYS = [
  "rate.reasons.style",
  "rate.reasons.verbose",
  "rate.reasons.unhelpful",
  "rate.reasons.incorrect",
  "rate.reasons.offTrack",
  "rate.reasons.refused",
  "rate.reasons.lazy",
  "rate.reasons.other",
] as const satisfies readonly MessageKey<"prep">[];

/** Built-in tag suggestions; submitted values are the resolved labels. */
const TAG_KEYS = [
  "rate.tags.education",
  "rate.tags.tech",
  "rate.tags.college",
  "rate.tags.prompting",
] as const satisfies readonly MessageKey<"prep">[];

export function RateModal({
  busy = false,
  onSubmit,
  onClose,
}: {
  busy?: boolean;
  onSubmit: (data: RateSubmit) => void;
  onClose: () => void;
}) {
  const t = useT("prep");
  const [score, setScore] = useState<number | null>(null);
  const [reasons, setReasons] = useState<string[]>([]);
  const [comment, setComment] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState("");

  const toggleReason = (key: (typeof REASON_KEYS)[number]) => {
    const label = t(key);
    setReasons((prev) => (prev.includes(label) ? prev.filter((r) => r !== label) : [...prev, label]));
  };

  const toggleTag = (key: (typeof TAG_KEYS)[number]) => {
    const label = t(key);
    setTags((prev) => (prev.includes(label) ? prev.filter((x) => x !== label) : [...prev, label]));
  };

  const addCustomTag = () => {
    const tag = tagInput.trim().slice(0, 30);
    if (!tag || tags.includes(tag)) return;
    setTags((prev) => [...prev, tag]);
    setTagInput("");
  };

  const isBuiltInTag = (tag: string) => TAG_KEYS.some((k) => t(k) === tag);
  const reasonActive = (key: (typeof REASON_KEYS)[number]) => reasons.includes(t(key));
  const tagActive = (key: (typeof TAG_KEYS)[number]) => tags.includes(t(key));

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 anim-fade-in"
      role="dialog"
      aria-modal="true"
      aria-label={t("rate.title")}
    >
      <div className="surface-card w-full max-w-lg !p-5 anim-rise">
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-[14px] font-semibold text-ink">{t("rate.title")}</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded p-1 text-ink-subtle transition-colors hover:bg-surface-muted hover:text-ink disabled:opacity-40"
            aria-label={t("rate.close")}
          >
            <X size={16} />
          </button>
        </div>

        <div className="mt-3 flex items-center justify-center gap-1.5">
          {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
            <button
              key={n}
              type="button"
              disabled={busy}
              onClick={() => setScore(n)}
              aria-pressed={score === n}
              aria-label={`${n}`}
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-full border text-[13px] transition-colors disabled:opacity-40",
                score === n
                  ? "border-[var(--primary)] bg-[var(--primary)] font-semibold text-white"
                  : "border-surface-border bg-surface-alt text-ink-muted hover:border-[var(--primary)] hover:text-ink",
              )}
            >
              {n}
            </button>
          ))}
        </div>
        <div className="mt-1.5 flex items-center justify-between text-[11px] text-ink-subtle">
          <span>{t("rate.scoreLow")}</span>
          <span>{t("rate.scoreHigh")}</span>
        </div>

        <p className="mt-4 text-[13px] font-medium text-ink">{t("rate.why")}</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {REASON_KEYS.map((key) => (
            <button
              key={key}
              type="button"
              disabled={busy}
              onClick={() => toggleReason(key)}
              aria-pressed={reasonActive(key)}
              className={cn(
                "rounded-full border px-3 py-1.5 text-[12px] transition-colors disabled:opacity-40",
                reasonActive(key)
                  ? "border-[var(--primary)] bg-[var(--primary)] text-white"
                  : "border-surface-border bg-surface-alt text-ink-muted hover:border-[var(--primary)] hover:text-ink",
              )}
            >
              {t(key)}
            </button>
          ))}
        </div>

        <textarea
          className="field-input mt-2.5 min-h-16 w-full resize-y"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder={t("rate.detailsPlaceholder")}
          disabled={busy}
          maxLength={2000}
        />

        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          {TAG_KEYS.map((key) => (
            <button
              key={key}
              type="button"
              disabled={busy}
              onClick={() => toggleTag(key)}
              aria-pressed={tagActive(key)}
              className={cn(
                "rounded-full border px-2.5 py-1 text-[11px] transition-colors disabled:opacity-40",
                tagActive(key)
                  ? "border-[var(--primary)] bg-[var(--primary)] text-white"
                  : "border-surface-border bg-surface-alt text-ink-muted hover:border-[var(--primary)] hover:text-ink",
              )}
            >
              {t(key)}
            </button>
          ))}
          <input
            className="field-input !h-7 !w-24 !px-2 !py-0 !text-[11px]"
            value={tagInput}
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addCustomTag()}
            placeholder={t("rate.addTagPlaceholder")}
            disabled={busy}
            maxLength={30}
          />
          <button
            type="button"
            onClick={addCustomTag}
            disabled={busy || !tagInput.trim()}
            className="flex h-6 w-6 items-center justify-center rounded-full border border-surface-border text-ink-subtle transition-colors hover:border-[var(--primary)] hover:text-ink disabled:opacity-40"
            aria-label={t("rate.addTag")}
          >
            <Plus size={13} />
          </button>
        </div>
        {tags.filter((x) => !isBuiltInTag(x)).length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {tags.filter((x) => !isBuiltInTag(x)).map((custom) => (
                <button
                  key={custom}
                  type="button"
                  disabled={busy}
                  onClick={() => setTags((prev) => prev.filter((x) => x !== custom))}
                  title={t("rate.removeTag")}
                  className="rounded-full border border-[var(--primary)] bg-[var(--primary)] px-2.5 py-1 text-[11px] text-white"
                >
                  {custom} ×
                </button>
              ))}
          </div>
        )}

        <div className="mt-4 flex justify-end">
          <button
            type="button"
            disabled={busy || score === null}
            onClick={() => onSubmit({ score: score ?? 0, reasons, comment: comment.trim(), tags })}
            className="btn-primary h-9 px-6"
          >
            {t("rate.save")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
