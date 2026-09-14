"use client";

/** Single model row: label, caps, and test/edit/delete actions. */

import { Check, Pencil, RefreshCw, Trash2 } from "lucide-react";
import type { ModelProfile } from "@/types";
import { useT } from "@/i18n";
import { CAP_OPTIONS, formatWindow } from "./constants";

export function ModelRow({
  model,
  testing,
  onEdit,
  onDelete,
  onTest,
}: {
  model: ModelProfile;
  testing: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onTest: () => void;
}) {
  const t = useT("settings");
  const caps = CAP_OPTIONS.filter(({ key }) => model.capabilities?.[key]).map(({ labelKey }) =>
    t(labelKey),
  );
  return (
    <div className="flex items-center gap-2 rounded-md border border-surface-border px-3 py-2">
      <span className="min-w-0 flex-1 truncate text-[13px] text-ink">
        {model.label}
        <span className="ml-2 text-[11px] text-ink-subtle">{model.provider_name}</span>
      </span>
      <span className="shrink-0 rounded bg-[var(--info-soft)] px-1.5 py-0.5 text-[10px] text-[var(--info-ink)]">
        {formatWindow(model.context_window)}
      </span>
      {caps.map((c) => (
        <span key={c} className="hidden shrink-0 rounded bg-surface-muted px-1.5 py-0.5 text-[10px] text-ink-muted sm:inline">
          {c}
        </span>
      ))}
      <button
        type="button"
        className="shrink-0 rounded p-1 text-ink-subtle transition-colors hover:bg-surface-muted hover:text-ink"
        onClick={onTest}
        aria-label={t("modelRow.test")}
      >
        {testing ? <RefreshCw size={13} className="animate-spin" /> : <Check size={13} />}
      </button>
      <button
        type="button"
        className="shrink-0 rounded p-1 text-ink-subtle transition-colors hover:bg-surface-muted hover:text-ink"
        onClick={onEdit}
        aria-label={t("modelRow.edit")}
      >
        <Pencil size={13} />
      </button>
      <button
        type="button"
        className="shrink-0 rounded p-1 text-ink-subtle transition-colors hover:bg-surface-muted hover:text-[var(--danger)]"
        onClick={onDelete}
        aria-label={t("modelRow.delete")}
      >
        <Trash2 size={13} />
      </button>
    </div>
  );
}
