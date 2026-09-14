"use client";

/** Interview setup local controls: Select / choice chips / empty-resume hint. */

import { useT } from "@/i18n";
import { Select as CustomSelect } from "@/components/Select";

export function Select({
  label,
  value,
  options,
  labels,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  labels?: string[];
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="field-label !mb-1 !text-xs">{label}</label>
      <CustomSelect
        className="!h-9 !text-xs"
        ariaLabel={label}
        value={value}
        options={options.map((o, i) => ({ value: o, label: labels?.[i] || o }))}
        onChange={onChange}
      />
    </div>
  );
}

/** Labeled chip group (company / personality); selected chip is highlighted. */
export function ChoiceGroup<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label?: string;
  value: T;
  options: { id: T; name: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div>
      {label && <label className="field-label !mb-2 !text-xs">{label}</label>}
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => {
          const selected = value === o.id;
          return (
            <button
              key={o.id}
              type="button"
              onClick={() => onChange(o.id)}
              className={`rounded-md border px-3 py-1.5 text-[12px] font-medium transition-all duration-base ease-google active:scale-[0.98] ${
                selected
                  ? "border-[var(--primary)] bg-[var(--info-soft)] text-[var(--info-ink)] shadow-focus"
                  : "border-surface-border bg-surface-card text-ink-muted hover:border-[var(--primary)] hover:bg-[var(--info-soft)] hover:text-[var(--info-ink)]"
              }`}
            >
              {o.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Compact multi-column company picker. */
export function CompanyGrid<T extends string>({
  value,
  companies,
  onChange,
}: {
  value: T;
  companies: { id: T; name: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-4 md:grid-cols-7">
      {companies.map((c) => {
        const selected = value === c.id;
        return (
          <button
            key={c.id}
            type="button"
            onClick={() => onChange(c.id)}
            className={`rounded-md border px-2 py-2 text-center text-[12px] font-medium transition-all duration-base ease-google active:scale-[0.98] ${
              selected
                ? "border-[var(--primary)] bg-[var(--info-soft)] text-[var(--info-ink)] shadow-focus"
                : "border-surface-border bg-surface-card text-ink-muted hover:border-[var(--primary)] hover:bg-[var(--info-soft)] hover:text-[var(--info-ink)]"
            }`}
          >
            {c.name}
          </button>
        );
      })}
    </div>
  );
}

/** Empty-resume warning block. */
export function ResumeWarning() {
  const t = useT("interview");
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-ink-muted">{t("setup.resume.label")}</label>
      <p className="rounded-md border border-[var(--warning)]/30 bg-[var(--warning-soft)] px-2.5 py-2 text-[11px] text-[var(--warning-ink)]">
        {t("setup.resume.empty")}
      </p>
    </div>
  );
}
