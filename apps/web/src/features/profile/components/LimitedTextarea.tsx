"use client";

/**
 * @file LimitedTextarea.tsx
 * @description Labeled textarea with character counter that warns near the limit.
 *
 * Responsibilities:
 * - Bind label to textarea via useId (same pattern as Field.tsx)
 * - Cap input length via maxLength and show live count
 * - Switch counter to danger color when near the limit
 * - Surface required and validation error states for accessibility
 *
 * Counter uses string.length (UTF-16 code units). Backend max_length is Python
 * code points; HTML maxLength is equal for BMP and the tighter cap for
 * astral/emoji, which is safe.
 */

import { useId } from "react";
import { useT } from "@/i18n";

/** Ratio of the limit at which the counter switches to warning color */
const NEAR_LIMIT_RATIO = 0.9;

/** Large text input with character counter; warning color near the limit */
export function LimitedTextarea({
  label,
  value,
  onChange,
  limit,
  rows,
  required = false,
  error = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  limit: number;
  rows: number;
  required?: boolean;
  error?: boolean;
}) {
  const t = useT("profile");
  const nearLimit = value.length >= limit * NEAR_LIMIT_RATIO;
  const id = useId();
  const errorId = useId();
  return (
    <div>
      <label htmlFor={id} className="field-label">
        {label}
        {required ? <span className="text-[var(--danger)]"> *</span> : null}
      </label>
      <textarea
        id={id}
        className={`field-textarea !leading-[1.7] ${error ? "field-invalid" : ""}`}
        rows={rows}
        maxLength={limit}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error || undefined}
        aria-required={required || undefined}
        aria-describedby={error ? errorId : undefined}
      />
      <p
        className={`mt-1 text-right text-[10px] tabular-nums ${
          nearLimit ? "text-[var(--danger-ink)]" : "text-ink-subtle"
        }`}
      >
        {value.length} / {limit}
      </p>
      {error && (
        <p id={errorId} className="field-error">
          {t("field.requiredError", { label })}
        </p>
      )}
    </div>
  );
}
