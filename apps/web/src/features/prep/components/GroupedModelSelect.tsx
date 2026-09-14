"use client";

/**
 * @file GroupedModelSelect.tsx
 * @description Model selector grouped by provider: cascading two-level menu
 * (provider list on the left, its models on the right). Falls back to the
 * flat ModelSelect when grouping data is absent or pointless.
 */

import { Check, ChevronDown, ChevronRight } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { useT } from "@/i18n";
import { ModelSelect, formatTokens } from "@/components/ModelControls";
import type { ModelProfile } from "@/types";

export function GroupedModelSelect({
  models,
  value,
  onChange,
  ariaLabel,
  defaultProfile,
}: {
  models: ModelProfile[];
  value: number | null;
  onChange: (id: number | null) => void;
  ariaLabel: string;
  defaultProfile?: ModelProfile | null;
}) {
  const t = useT("common");
  const [open, setOpen] = useState(false);
  const [activeProvider, setActiveProvider] = useState("");
  const listId = useId();

  // Provider groups in first-appearance order; models keep backend order.
  const groups = useMemo(() => {
    const order: string[] = [];
    const byProvider = new Map<string, ModelProfile[]>();
    for (const m of models) {
      const provider = (m.provider_name ?? "").trim();
      if (!provider) return [];
      if (!byProvider.has(provider)) {
        byProvider.set(provider, []);
        order.push(provider);
      }
      byProvider.get(provider)?.push(m);
    }
    return order.map((provider) => ({
      provider,
      models: byProvider.get(provider) ?? [],
    }));
  }, [models]);
  const hasGrouping = groups.length >= 2;

  // Identical to ModelSelect: null follows the default profile when listed.
  const effectiveValue =
    value ?? (defaultProfile && models.some((m) => m.id === defaultProfile.id) ? defaultProfile.id : "");
  const selected = models.find((m) => m.id === effectiveValue) ?? null;
  const selectedProvider = (selected?.provider_name ?? "").trim();
  const activeModels = groups.find((g) => g.provider === activeProvider)?.models ?? [];
  // Window suffix: the effective context window travels with the label so a
  // mismatch between the configured value and the runtime budget is visible.
  const labelWithWindow = (m: ModelProfile) =>
    m.context_window > 0 ? `${m.label} · ${formatTokens(m.context_window)}` : m.label;

  if (!hasGrouping) {
    return (
      <ModelSelect
        models={models}
        value={value}
        onChange={onChange}
        ariaLabel={ariaLabel}
        defaultProfile={defaultProfile}
      />
    );
  }

  const openMenu = () => {
    setActiveProvider(selectedProvider || groups[0]?.provider || "");
    setOpen(true);
  };

  return (
    <div className="relative min-w-0 shrink-0">
      <button
        type="button"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={ariaLabel}
        onClick={() => (open ? setOpen(false) : openMenu())}
        onKeyDown={(e) => {
          if (e.key === "Escape" && open) {
            e.preventDefault();
            setOpen(false);
          }
        }}
        className="flex h-7 w-auto min-w-0 max-w-[220px] items-center justify-between gap-1.5 rounded-md bg-transparent px-1.5 text-[12px] text-ink transition-colors hover:bg-surface-muted focus:outline-none focus-visible:bg-surface-muted"
      >
        <span className="flex min-w-0 flex-1 items-baseline gap-1.5" title={selected ? labelWithWindow(selected) : undefined}>
          <span className="min-w-0 flex-1 truncate">
            {selected?.label ?? (!defaultProfile ? t("model.notSet") : "")}
          </span>
          {selected && selected.context_window > 0 ? (
            <span className="shrink-0 text-[10px] text-ink-subtle">{formatTokens(selected.context_window)}</span>
          ) : null}
        </span>
        <ChevronDown size={14} className="shrink-0 text-ink-subtle" />
      </button>
      {open && (
        <>
          {/* Click outside the menu to close */}
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} aria-hidden />
          <div
            role="listbox"
            id={listId}
            aria-label={ariaLabel}
            className="surface-card absolute bottom-full right-0 z-40 mb-2 flex max-h-64 w-[380px] max-w-[calc(100vw-2rem)] overflow-hidden !p-1 shadow-lg"
          >
            {/* Provider list: hover or click drives the model column. */}
            <div className="w-36 shrink-0 overflow-y-auto border-r border-surface-border p-1">
              {groups.map((g) => {
                const focused = g.provider === activeProvider;
                return (
                  <button
                    key={g.provider}
                    type="button"
                    role="menuitem"
                    aria-label={g.provider}
                    onMouseEnter={() => setActiveProvider(g.provider)}
                    onClick={() => setActiveProvider(g.provider)}
                    className={`flex w-full items-center gap-1 rounded-md px-2.5 py-2 text-left text-[12px] transition-colors ${
                      focused ? "bg-surface-muted font-medium text-ink" : "text-ink-muted"
                    }`}
                  >
                    <span className="min-w-0 flex-1 truncate">{g.provider}</span>
                    <ChevronRight size={13} className="shrink-0 text-ink-subtle" />
                  </button>
                );
              })}
            </div>
            {/* Models of the active provider. */}
            <div className="min-w-0 flex-1 overflow-y-auto p-1">
              {!defaultProfile && (
                <button
                  key="__unset"
                  type="button"
                  role="option"
                  aria-selected={effectiveValue === ""}
                  onClick={() => {
                    onChange(null);
                    setOpen(false);
                  }}
                  className={`flex h-9 w-full cursor-pointer items-center justify-between gap-2 rounded-md px-2.5 text-left text-[13px] transition-colors ${
                    effectiveValue === ""
                      ? "bg-surface-muted font-medium text-[var(--primary)]"
                      : "text-ink hover:bg-surface-muted"
                  }`}
                >
                  <span className="min-w-0 truncate">{t("model.notSet")}</span>
                  {effectiveValue === "" && <Check size={14} className="shrink-0" />}
                </button>
              )}
              {activeModels.map((m) => {
                const active = m.id === effectiveValue;
                return (
                  <button
                    key={m.id}
                    type="button"
                    role="option"
                    aria-selected={active}
                    onClick={() => {
                      onChange(m.id);
                      setOpen(false);
                    }}
                    title={labelWithWindow(m)}
                    className={`flex h-9 w-full cursor-pointer items-center justify-between gap-2 rounded-md px-2.5 text-left text-[13px] transition-colors ${
                      active
                        ? "bg-surface-muted font-medium text-[var(--primary)]"
                        : "text-ink hover:bg-surface-muted"
                    }`}
                  >
                    <span className="min-w-0 truncate">{labelWithWindow(m)}</span>
                    {active && <Check size={14} className="shrink-0" />}
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
