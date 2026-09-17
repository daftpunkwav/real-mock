"use client";

/** Left column: configured providers plus a "+" toggle that reveals the add panel. */

import { useState } from "react";
import { ChevronRight, Plus } from "lucide-react";
import { useT } from "@/i18n";
import type { ProviderWithModels } from "@/types";
import { AddProviderPanel } from "./AddProviderPanel";

export function ProviderList({
  providers,
  selectedId,
  onSelect,
  onApplyVendor,
  onCreated,
}: {
  providers: ProviderWithModels[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onApplyVendor: (vendorId: string) => Promise<void>;
  onCreated: (providerId: number) => Promise<void>;
}) {
  const [adding, setAdding] = useState(false);
  const t = useT("settings");

  return (
    <div className="surface-card !p-3">
      <div className="mb-2 flex items-center justify-between px-1">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-subtle">
          {t("providerList.title")}
        </p>
        <button
          type="button"
          className={`flex h-6 w-6 items-center justify-center rounded-md border transition-colors ${
            adding
              ? "border-[var(--primary)] bg-[var(--info-soft)] text-ink"
              : "border-surface-border text-ink-muted hover:border-[var(--primary)] hover:text-ink"
          }`}
          aria-label={t("providerList.add")}
          onClick={() => setAdding((v) => !v)}
        >
          <Plus size={13} />
        </button>
      </div>
      <div className="space-y-1">
        {providers.length === 0 && !adding && (
          <p className="px-1 text-[12px] text-ink-subtle">{t("providerList.empty")}</p>
        )}
        {providers.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => onSelect(p.id)}
            className={`flex w-full items-center gap-2 rounded-md border px-2.5 py-2 text-left text-[13px] transition-colors ${
              p.id === selectedId
                ? "border-[var(--primary)] bg-[var(--info-soft)] text-ink"
                : "border-transparent text-ink-muted hover:bg-surface-muted"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 shrink-0 rounded-full ${p.enabled ? "bg-[var(--success)]" : "bg-ink-subtle"}`}
            />
            <span className="min-w-0 flex-1 truncate">{p.name}</span>
            <span className="shrink-0 text-[10px] text-ink-subtle">{p.models.length}</span>
            <ChevronRight size={13} className="shrink-0 text-ink-subtle" />
          </button>
        ))}
      </div>

      {adding && (
        <AddProviderPanel
          onClose={() => setAdding(false)}
          onApplyVendor={onApplyVendor}
          onCreated={onCreated}
        />
      )}
    </div>
  );
}
