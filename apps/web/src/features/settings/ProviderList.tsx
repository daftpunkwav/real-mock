"use client";

/** Left : + . */

import { useState } from "react";
import { ChevronRight, Plus } from "lucide-react";
import { settingsHttp } from "@/lib/api/clients";
import { toast } from "@/components/Toast";
import { useT } from "@/i18n";
import type { ProviderWithModels } from "@/types";
import { RecommendedVendors } from "./RecommendedVendors";

export function ProviderList({
  providers,
  selectedId,
  onSelect,
  onChanged,
}: {
  providers: ProviderWithModels[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onChanged: () => Promise<void>;
}) {
  const [newProviderName, setNewProviderName] = useState("");
  const t = useT("settings");

  const create = async () => {
    try {
      await settingsHttp.createProvider({ name: newProviderName.trim() });
      setNewProviderName("");
      await onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("providerList.createFailed"));
    }
  };

  return (
    <div className="surface-card !p-3">
      <p className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-wider text-ink-subtle">
        {t("providerList.title")}
      </p>
      <div className="space-y-1">
        {providers.length === 0 && (
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

      <div className="mt-3 border-t border-surface-border pt-3">
        <label className="mb-1 block text-[11px] text-ink-muted">{t("providerList.addLabel")}</label>
        <div className="flex gap-1.5">
          <input
            className="field-input !h-8 flex-1 text-[12px]"
            placeholder={t("providerList.namePlaceholder")}
            value={newProviderName}
            onChange={(e) => setNewProviderName(e.target.value)}
          />
          <button
            type="button"
            className="btn-primary !h-8 !w-8 shrink-0 !p-0"
            aria-label={t("providerList.add")}
            disabled={!newProviderName.trim()}
            onClick={create}
          >
            <Plus size={14} />
          </button>
        </div>
      </div>

      <RecommendedVendors providers={providers} onChanged={onChanged} onSelect={onSelect} />
    </div>
  );
}
