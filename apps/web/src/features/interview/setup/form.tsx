"use client";

/** Interview setup selectors: strictness labels, resume, and processor cards. */

import { useT } from "@/i18n";
import { Mic } from "lucide-react";
import type { ModelProfile, ReasoningEffort, ResumePickerItem } from "@/types";
import { EffortSelect, ModelSelect } from "@/components/ModelControls";
import { Select } from "./controls";

export type StrictnessLabelKey =
  | "setup.strictness.friendly"
  | "setup.strictness.normal"
  | "setup.strictness.high"
  | "setup.strictness.extreme";

/** Map a strictness score to its label key. */
export function strictnessLabelKey(strictness: number): StrictnessLabelKey {
  return strictness <= 3
    ? "setup.strictness.friendly"
    : strictness <= 6
      ? "setup.strictness.normal"
      : strictness <= 8
        ? "setup.strictness.high"
        : "setup.strictness.extreme";
}

export function ResumeSelect({
  resumes,
  value,
  onChange,
}: {
  resumes: ResumePickerItem[];
  value: number | null;
  onChange: (v: number | null) => void;
}) {
  const t = useT("interview");
  return (
    <Select
      label={t("setup.resume.label")}
      value={String(value)}
      options={resumes.map((r) => String(r.id))}
      labels={resumes.map((r) => (r.is_active ? t("setup.resume.activeItem", { name: r.filename }) : r.filename))}
      onChange={(v) => onChange(Number(v))}
    />
  );
}

export function ProcessorCard({
  chatModels,
  sttModels,
  ttsModels,
  chatModelId,
  sttModelId,
  ttsModelId,
  effort,
  setChatModelId,
  setSttModelId,
  setTtsModelId,
  setEffort,
  defaultBindings,
  disabled,
}: {
  chatModels: ModelProfile[];
  sttModels: ModelProfile[];
  ttsModels: ModelProfile[];
  chatModelId: number | null;
  sttModelId: number | null;
  ttsModelId: number | null;
  effort: ReasoningEffort;
  setChatModelId: (v: number | null) => void;
  setSttModelId: (v: number | null) => void;
  setTtsModelId: (v: number | null) => void;
  setEffort: (v: ReasoningEffort) => void;
  defaultBindings: import("@/types").TaskBindings | null;
  disabled: boolean;
}) {
  const t = useT("interview");
  return (
    <div className="surface-card p-3.5">
      <p className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold text-ink">
        <Mic size={13} className="text-[var(--primary)]" />
        {t("setup.processor.title")}
      </p>
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label className="field-label !mb-1 !text-xs">{t("setup.processor.chatModel")}</label>
          <ModelSelect
            models={chatModels}
            value={chatModelId}
            onChange={setChatModelId}
            disabled={disabled}
            ariaLabel={t("setup.processor.chatModel")}
            className="!w-full !max-w-none"
            defaultProfile={defaultBindings?.chat?.profile ?? null}
          />
        </div>
        <div>
          <label className="field-label !mb-1 !text-xs">{t("setup.processor.effort")}</label>
          <EffortSelect
            model={chatModels.find((m) => m.id === chatModelId) ?? null}
            value={effort}
            onChange={setEffort}
            disabled={disabled}
            forceVisible
            hideIcon
            className="!w-full"
          />
        </div>
        <div>
          <label className="field-label !mb-1 !text-xs">{t("setup.processor.stt")}</label>
          <ModelSelect
            models={sttModels}
            value={sttModelId}
            onChange={setSttModelId}
            disabled={disabled}
            ariaLabel={t("setup.processor.sttAria")}
            className="!w-full !max-w-none"
            defaultProfile={defaultBindings?.stt?.profile ?? null}
          />
        </div>
        <div>
          <label className="field-label !mb-1 !text-xs">{t("setup.processor.tts")}</label>
          <ModelSelect
            models={ttsModels}
            value={ttsModelId}
            onChange={setTtsModelId}
            disabled={disabled}
            ariaLabel={t("setup.processor.ttsAria")}
            className="!w-full !max-w-none"
            defaultProfile={defaultBindings?.tts?.profile ?? null}
          />
        </div>
      </div>
    </div>
  );
}
