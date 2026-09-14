"use client";

/**
 * @file Field.tsx
 * @description Single-line labeled text input with required and validation error states.
 *
 * Responsibilities:
 * - Bind label to input for screen readers via useId (keep in sync with LimitedTextarea)
 * - Surface required marker and field-level error messaging
 * - Enforce optional maxLength on the native input
 */

import { useId } from "react";
import { useT } from "@/i18n";

export function Field({
  label,
  value,
  onChange,
  className = "",
  required = false,
  error = false,
  maxLength,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  className?: string;
  required?: boolean;
  error?: boolean;
  maxLength?: number;
}) {
  const t = useT("profile");
  // Associate label with input for screen readers; error text via describedby
  const id = useId();
  const errorId = useId();
  return (
    <div className={className}>
      <label htmlFor={id} className="field-label !mb-1.5 !text-xs">
        {label}
        {required ? <span className="text-[var(--danger)]"> *</span> : null}
      </label>
      <input
        id={id}
        type="text"
        className={`field-input !text-[13px] ${error ? "field-invalid" : ""}`}
        value={value}
        maxLength={maxLength}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error || undefined}
        aria-required={required || undefined}
        aria-describedby={error ? errorId : undefined}
      />
      {error && (
        <p id={errorId} className="field-error">
          {t("field.requiredError", { label })}
        </p>
      )}
    </div>
  );
}
