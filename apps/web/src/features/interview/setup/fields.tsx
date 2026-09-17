"use client";

/** Interview setup form cards: goal (role/company) + format (type/style/rounds/persona)
 * + presenter (avatar/scene/resume) + processor selection. */

import { useLocale, useT } from "@/i18n";
import { Briefcase, ListChecks, UserCircle } from "lucide-react";
import type {
  InterviewConfig,
  Options,
  ResumePickerItem,
} from "@/lib/api/contract";
import type {
  ModelProfile,
  ReasoningEffort,
  ReferenceDetail,
  TaskBindings,
} from "@/types";
import { CompanyGrid, ResumeWarning, Select } from "./controls";
import { ProcessorCard } from "./processorCard";
import {
  CUSTOM_COMPANY_ID,
  CUSTOM_ROLE_ID,
  avatarLabel,
  isPresetCompany,
  isPresetRole,
  levelLabel,
  localizeOptions,
  personalityLabel,
  roleLabel,
  sceneLabel,
  styleLabel,
  voiceLabel,
  workflowLabel,
} from "./optionLabels";

function CardTitle({
  icon: Icon,
  text,
}: {
  icon: React.ComponentType<{ size?: number; className?: string; strokeWidth?: number }>;
  text: string;
}) {
  return (
    <h2 className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold text-ink">
      <Icon size={14} className="text-[var(--primary)]" strokeWidth={1.75} />
      {text}
    </h2>
  );
}

export type StrictnessLabelKey =
  | "setup.strictness.easy"
  | "setup.strictness.friendly"
  | "setup.strictness.balanced"
  | "setup.strictness.strict"
  | "setup.strictness.harsh"
  | "setup.strictness.relentless";

/** Six named strictness levels mapped onto the 1-10 scale the backend stores. */
export const STRICTNESS_LEVELS: { value: number; labelKey: StrictnessLabelKey }[] = [
  { value: 1, labelKey: "setup.strictness.easy" },
  { value: 3, labelKey: "setup.strictness.friendly" },
  { value: 5, labelKey: "setup.strictness.balanced" },
  { value: 7, labelKey: "setup.strictness.strict" },
  { value: 9, labelKey: "setup.strictness.harsh" },
  { value: 10, labelKey: "setup.strictness.relentless" },
];

/** Nearest named level for an arbitrary strictness value (legacy configs too). */
export function strictnessLevelIndex(strictness: number): number {
  let bestIndex = 0;
  let bestDiff = Infinity;
  STRICTNESS_LEVELS.forEach((level, i) => {
    const diff = Math.abs(level.value - strictness);
    if (diff < bestDiff) {
      bestDiff = diff;
      bestIndex = i;
    }
  });
  return bestIndex;
}

export function strictnessLabelKey(strictness: number): StrictnessLabelKey {
  return STRICTNESS_LEVELS[strictnessLevelIndex(strictness)]?.labelKey ?? "setup.strictness.balanced";
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

export function SetupFields({
  options,
  config,
  resumes,
  creating,
  multiRound,
  onMultiRound,
  chatModels,
  sttModels,
  ttsModels,
  chatModelId,
  sttModelId,
  ttsModelId,
  effort,
  referenceDetail,
  defaultBindings,
  onConfig,
  setChatModelId,
  setSttModelId,
  setTtsModelId,
  setEffort,
  setReferenceDetail,
  footer,
}: {
  options: Options;
  config: InterviewConfig;
  resumes: ResumePickerItem[];
  creating: boolean;
  multiRound: boolean;
  onMultiRound: (v: boolean) => void;
  chatModels: ModelProfile[];
  sttModels: ModelProfile[];
  ttsModels: ModelProfile[];
  chatModelId: number | null;
  sttModelId: number | null;
  ttsModelId: number | null;
  effort: ReasoningEffort;
  referenceDetail: ReferenceDetail;
  defaultBindings: TaskBindings | null;
  onConfig: (patch: Partial<InterviewConfig>) => void;
  setChatModelId: (v: number | null) => void;
  setSttModelId: (v: number | null) => void;
  setTtsModelId: (v: number | null) => void;
  setEffort: (v: ReasoningEffort) => void;
  setReferenceDetail: (v: ReferenceDetail) => void;
  footer?: React.ReactNode;
}) {
  const t = useT("interview");
  const { locale } = useLocale();
  const localized = localizeOptions(options, t, locale);
  const roleSelectValue = isPresetRole(config.role, options.roles)
    ? config.role
    : CUSTOM_ROLE_ID;
  const customRoleText = roleSelectValue === CUSTOM_ROLE_ID ? config.role : "";
  const companyIsCustom = !isPresetCompany(config.company, options.companies);
  const customCompanyText = companyIsCustom ? config.company : "";

  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-y-auto pb-2 pr-0.5">
      <div className="surface-card p-3.5">
        <CardTitle icon={Briefcase} text={t("setup.section.goal")} />
        <div className="grid grid-cols-2 gap-2.5">
          <Select
            label={t("setup.role.label")}
            value={roleSelectValue}
            options={[CUSTOM_ROLE_ID, ...options.roles]}
            labels={[roleLabel(CUSTOM_ROLE_ID, t), ...localized.roleLabels]}
            onChange={(v) => {
              if (v === CUSTOM_ROLE_ID) onConfig({ role: "" });
              else onConfig({ role: v });
            }}
          />
          <Select
            label={t("setup.level.label")}
            value={config.level}
            options={options.levels}
            labels={options.levels.map((id) => levelLabel(id, t))}
            onChange={(v) => onConfig({ level: v })}
          />
        </div>
        {roleSelectValue === CUSTOM_ROLE_ID && (
          <div className="mt-2.5">
            <label className="field-label !mb-1 !text-xs">{t("setup.role.custom")}</label>
            <input
              type="text"
              value={customRoleText}
              placeholder={t("setup.role.customPlaceholder")}
              onChange={(e) => onConfig({ role: e.target.value })}
              className="field-input !h-9 !text-xs"
            />
          </div>
        )}
        <div className="mt-3">
          <label className="field-label !mb-2 !text-xs">{t("setup.company.label")}</label>
          <CompanyGrid
            value={companyIsCustom ? CUSTOM_COMPANY_ID : config.company}
            companies={[
              { id: CUSTOM_COMPANY_ID, name: t("setup.company.custom") },
              ...localized.companies.map((c) => ({ id: c.id, name: c.name })),
            ]}
            onChange={(v) => onConfig({ company: v === CUSTOM_COMPANY_ID ? "" : v })}
          />
        </div>
        {companyIsCustom && (
          <div className="mt-2.5">
            <label className="field-label !mb-1 !text-xs">{t("setup.company.custom")}</label>
            <input
              type="text"
              value={customCompanyText}
              maxLength={100}
              placeholder={t("setup.company.customPlaceholder")}
              onChange={(e) => onConfig({ company: e.target.value })}
              className="field-input !h-9 !text-xs"
            />
          </div>
        )}
      </div>

      <div className="surface-card p-3.5">
        <CardTitle icon={ListChecks} text={t("setup.section.format")} />
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          <Select
            label={t("setup.type.label")}
            value={config.workflow_type}
            options={options.workflow_types.map((w) => w.id)}
            labels={options.workflow_types.map((w) => workflowLabel(w.id, t))}
            onChange={(v) => onConfig({ workflow_type: v as InterviewConfig["workflow_type"] })}
          />
          <Select
            label={t("setup.style.label")}
            value={config.interview_style}
            options={options.interview_styles.map((s) => s.id)}
            labels={options.interview_styles.map((s) => styleLabel(s.id, t))}
            onChange={(v) => onConfig({ interview_style: v as InterviewConfig["interview_style"] })}
          />
          <Select
            label={t("setup.rounds.label")}
            value={multiRound ? "multi" : "single"}
            options={["single", "multi"]}
            labels={[t("setup.rounds.single"), t("setup.rounds.multi")]}
            onChange={(v) => onMultiRound(v === "multi")}
          />
          {options.scenes && options.scenes.length > 0 && (
            <Select
              label={t("setup.scene.label")}
              value={config.scene_id || "meeting_room"}
              options={options.scenes.map((s) => s.id)}
              labels={options.scenes.map((s) => sceneLabel(s.id, t))}
              onChange={(v) => onConfig({ scene_id: v })}
            />
          )}
        </div>
      </div>

      <div className="surface-card p-3.5">
        <CardTitle icon={UserCircle} text={t("setup.section.presenter")} />
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          {options.avatars && options.avatars.length > 0 && (
            <Select
              label={t("setup.avatar.label")}
              value={config.avatar_id || "professional_male"}
              options={options.avatars.map((a) => a.id)}
              labels={options.avatars.map((a) => {
                const name = avatarLabel(a.id, locale);
                const voiceName = a.voice
                  ? voiceLabel(a.voice, t)
                  : "";
                return voiceName ? t("setup.avatar.voiceMatch", { name, voice: voiceName }) : name;
              })}
              onChange={(v) => onConfig({ avatar_id: v })}
            />
          )}
          <Select
            label={t("setup.personality.label")}
            value={config.personality}
            options={options.personalities.map((p) => p.id)}
            labels={options.personalities.map((p) => personalityLabel(p.id, t))}
            onChange={(v) => onConfig({ personality: v as InterviewConfig["personality"] })}
          />
          <Select
            label={t("setup.strictness.label")}
            value={String(strictnessLevelIndex(config.strictness))}
            options={STRICTNESS_LEVELS.map((_, i) => String(i))}
            labels={STRICTNESS_LEVELS.map((l) => t(l.labelKey))}
            onChange={(v) =>
              onConfig({ strictness: STRICTNESS_LEVELS[Number(v)]?.value ?? config.strictness })
            }
          />
          {resumes.length > 0 ? (
            <ResumeSelect resumes={resumes} value={config.resume_id ?? null} onChange={(v) => onConfig({ resume_id: v })} />
          ) : (
            <ResumeWarning />
          )}
        </div>
      </div>

      <ProcessorCard
        chatModels={chatModels}
        sttModels={sttModels}
        ttsModels={ttsModels}
        chatModelId={chatModelId}
        sttModelId={sttModelId}
        ttsModelId={ttsModelId}
        effort={effort}
        referenceDetail={referenceDetail}
        setChatModelId={setChatModelId}
        setSttModelId={setSttModelId}
        setTtsModelId={setTtsModelId}
        setEffort={setEffort}
        setReferenceDetail={setReferenceDetail}
        defaultBindings={defaultBindings}
        disabled={creating}
      />

      {footer}
    </div>
  );
}
