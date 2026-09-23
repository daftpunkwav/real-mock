"use client";

/** Model dropdown and reasoning-effort selector. */

import { memo } from "react";
import { Brain } from "lucide-react";
import type { ModelProfile, ReasoningEffort } from "@/types";
import { useT, type MessageKey } from "@/i18n";
import { Select } from "@/components/Select";

/** Effort options; label is an i18n key resolved at render (cannot call useT at module top level). */
export const EFFORT_OPTIONS: {
  value: ReasoningEffort;
  labelKey: MessageKey<"common">;
}[] = [
  { value: "low", labelKey: "model.effort.low" },
  { value: "medium", labelKey: "model.effort.medium" },
  { value: "high", labelKey: "model.effort.high" },
  { value: "max", labelKey: "model.effort.max" },
];

/** Custom thinking levels declared on the model (extras.reasoning.variants);
 * labels outside the default scale are passed verbatim to the provider. */
export function modelEffortOptions(model: ModelProfile | null): ReasoningEffort[] {
  const reasoning = model?.extras?.reasoning;
  if (typeof reasoning === "object" && reasoning !== null && !Array.isArray(reasoning)) {
    const raw = (reasoning as Record<string, unknown>).variants;
    if (Array.isArray(raw)) {
      const cleaned = raw
        .map((v) => String(v).trim())
        .filter((v) => v.length > 0)
        .slice(0, 8);
      if (cleaned.length > 0) return cleaned;
    }
  }
  return EFFORT_OPTIONS.map((o) => o.value);
}

/** Model select (value=profile id; null=follow default handler binding, shown as a normal selected item) */
export const ModelSelect = memo(function ModelSelect({
  models,
  value,
  onChange,
  disabled,
  className,
  ariaLabel,
  defaultProfile,
}: {
  models: ModelProfile[];
  value: number | null;
  onChange: (id: number | null) => void;
  disabled?: boolean;
  className?: string;
  ariaLabel: string;
  defaultProfile?: ModelProfile | null;
}) {
  const t = useT("common");
  const boundDefault =
    defaultProfile && models.some((m) => m.id === defaultProfile.id) ? defaultProfile : null;
  const effectiveValue = value ?? boundDefault?.id ?? "";
  // The empty option is always offered: null means "follow the default binding"
  // (task binding → legacy stage config → local/edge fallback), so clearing back
  // to default must stay reachable even when a default profile exists.
  const emptyLabel = boundDefault
    ? t("model.useDefault", { label: boundDefault.label })
    : t("model.notSet");
  return (
    <Select
      className={`w-auto max-w-[210px] !py-0 text-[12px] ${className ?? ""}`}
      ariaLabel={ariaLabel}
      value={effectiveValue}
      options={[
        { value: "" as const, label: emptyLabel },
        ...models.map((m) => ({ value: m.id, label: m.label })),
      ]}
      onChange={(v) => onChange(v === "" ? null : Number(v))}
      disabled={disabled}
    />
  );
});

/** Effort select; hidden when the model lacks reasoning and forceVisible is false.
 * forceVisible keeps selector for default-model config; unsupported effort sent as null (see usePrepSend).
 * hideIcon drops the leading Brain (labeled forms already name the field; the toolbar keeps it). */
export const EffortSelect = memo(function EffortSelect({
  model,
  value,
  onChange,
  disabled,
  forceVisible = false,
  hideIcon = false,
  className,
}: {
  model: ModelProfile | null;
  value: ReasoningEffort;
  onChange: (e: ReasoningEffort) => void;
  disabled?: boolean;
  forceVisible?: boolean;
  hideIcon?: boolean;
  className?: string;
}) {
  const t = useT("common");
  if (!forceVisible && !model?.capabilities.reasoning) return null;
  // Model-declared custom levels win; default four-level scale otherwise.
  const options = modelEffortOptions(model).map((value) => {
    const known = EFFORT_OPTIONS.find((o) => o.value === value);
    return { value, label: known ? t(known.labelKey) : value };
  });
  return (
    <div className="flex w-full items-center gap-1.5">
      {!hideIcon && <Brain size={14} className="shrink-0 text-ink-subtle" />}
      <Select
        className={`w-auto flex-1 !py-0 text-[12px] ${className ?? ""}`}
        ariaLabel={t("model.effort.aria")}
        value={value}
        options={options}
        onChange={onChange}
        disabled={disabled}
      />
    </div>
  );
});
