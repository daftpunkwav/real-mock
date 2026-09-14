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
  const effectiveValue =
    value ?? (defaultProfile && models.some((m) => m.id === defaultProfile.id) ? defaultProfile.id : "");
  return (
    <Select
      className={`w-auto max-w-[210px] !py-0 text-[12px] ${className ?? ""}`}
      ariaLabel={ariaLabel}
      value={effectiveValue}
      options={[
        ...(!defaultProfile ? [{ value: "" as const, label: t("model.notSet") }] : []),
        ...models.map((m) => ({ value: m.id, label: m.label })),
      ]}
      onChange={(v) => onChange(v === "" ? null : Number(v))}
      disabled={disabled}
    />
  );
});

/** Effort select; hidden when the model lacks reasoning and forceVisible is false.
 * forceVisible keeps selector for default-model config; unsupported effort sent as null (see usePrepSend). */
export const EffortSelect = memo(function EffortSelect({
  model,
  value,
  onChange,
  disabled,
  forceVisible = false,
}: {
  model: ModelProfile | null;
  value: ReasoningEffort;
  onChange: (e: ReasoningEffort) => void;
  disabled?: boolean;
  forceVisible?: boolean;
}) {
  const t = useT("common");
  if (!forceVisible && !model?.capabilities.reasoning) return null;
  return (
    <div className="flex items-center gap-1">
      <Brain size={14} className="shrink-0 text-ink-subtle" />
      <Select
        className="w-auto !py-0 text-[12px]"
        ariaLabel={t("model.effort.aria")}
        value={value}
        options={EFFORT_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
        onChange={onChange}
        disabled={disabled}
      />
    </div>
  );
});
