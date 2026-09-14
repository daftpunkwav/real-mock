"use client";

/** chat / stt / tts . */

import type { ModelProfile, TaskBindings } from "@/types";
import { getTranslator, useT } from "@/i18n";
import { Select } from "@/components/Select";
import { TASK_META, modelsForTask } from "./constants";

export function BindingsCard({
  bindings,
  allModels,
  onUpdate,
}: {
  bindings: TaskBindings | null;
  allModels: ModelProfile[];
  onUpdate: (task: "chat" | "stt" | "tts", profileId: number) => void;
}) {
  const t = useT("settings");

  return (
    <div className="surface-card !p-4">
      <h2 className="mb-1 text-[13px] font-semibold text-ink">{t("bindings.title")}</h2>
      <p className="mb-3 text-[11px] text-ink-subtle">{t("bindings.desc")}</p>
      <div className="space-y-3">
        {TASK_META.map(({ task, labelKey, hintKey, capKey }) => (
          <div key={task} className="flex flex-wrap items-center gap-2">
            <span className="w-32 shrink-0 text-[12px] font-medium text-ink">{t(labelKey)}</span>
            {bindingSelect(bindings, allModels, task, capKey, onUpdate)}
            <span
              className="min-w-0 flex-1 basis-48 truncate text-[11px] text-ink-subtle"
              title={t(hintKey)}
            >
              {t(hintKey)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function bindingSelect(
  bindings: TaskBindings | null,
  allModels: ModelProfile[],
  task: "chat" | "stt" | "tts",
  capKey: keyof ModelProfile["capabilities"],
  onUpdate: (task: "chat" | "stt" | "tts", profileId: number) => void,
) {
  // Use a translator outside React; hooks are unavailable here.
  const t = getTranslator("settings");
  const binding = bindings?.[task];
  const options = modelsForTask(allModels, capKey);
  const currentId = binding?.profile?.id ?? null;
  return (
    <Select
      className="!h-8 !py-0 text-[12px]"
      ariaLabel={t("bindings.selectAria", { task })}
      value={currentId ?? ""}
      options={[
        { value: "", label: options.length ? t("bindings.unset") : t("bindings.noModels") },
        ...options.map((m) => ({
          value: m.id,
          label: t("bindings.optionLabel", { label: m.label, provider: m.provider_name }),
        })),
      ]}
      onChange={(v) => {
        const id = v === "" ? null : Number(v);
        if (id) onUpdate(task, id);
      }}
      disabled={!options.length}
    />
  );
}
