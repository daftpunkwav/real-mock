"use client";

/** Interview setup form cards: role/level/type/style + company + personality + avatar/scene/resume. */

import { useLocale, useT } from "@/i18n";
import type {
  InterviewConfig,
  Options,
  ResumePickerItem,
} from "@/lib/api/contract";
import type {
  ModelProfile,
  ReasoningEffort,
  TaskBindings,
} from "@/types";
import { ChoiceGroup, CompanyGrid, ResumeWarning, Select } from "./controls";
import { ProcessorCard, ResumeSelect, strictnessLabelKey } from "./form";
import {
  CUSTOM_ROLE_ID,
  avatarLabel,
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
  defaultBindings,
  onConfig,
  setChatModelId,
  setSttModelId,
  setTtsModelId,
  setEffort,
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
  defaultBindings: TaskBindings | null;
  onConfig: (patch: Partial<InterviewConfig>) => void;
  setChatModelId: (v: number | null) => void;
  setSttModelId: (v: number | null) => void;
  setTtsModelId: (v: number | null) => void;
  setEffort: (v: ReasoningEffort) => void;
  footer?: React.ReactNode;
}) {
  const t = useT("interview");
  const { locale } = useLocale();
  const localized = localizeOptions(options, t, locale);
  const roleSelectValue = isPresetRole(config.role, options.roles)
    ? config.role
    : CUSTOM_ROLE_ID;
  const customRoleText = roleSelectValue === CUSTOM_ROLE_ID ? config.role : "";

  return (
    <div className="flex min-h-0 flex-col gap-3 overflow-y-auto pb-2 pr-0.5">
      <div className="surface-card p-3.5">
        <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
          <Select
            label={t("setup.role.label")}
            value={roleSelectValue}
            options={[...options.roles, CUSTOM_ROLE_ID]}
            labels={[...localized.roleLabels, roleLabel(CUSTOM_ROLE_ID, t)]}
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
      </div>

      <div className="surface-card p-3.5">
        <label className="field-label !mb-2 !text-xs">{t("setup.company.label")}</label>
        <CompanyGrid
          value={config.company}
          companies={localized.companies.map((c) => ({ id: c.id, name: c.name }))}
          onChange={(v) => onConfig({ company: v })}
        />
      </div>

      <div className="surface-card p-3.5">
        <ChoiceGroup
          label={t("setup.rounds.label")}
          value={multiRound ? "multi" : "single"}
          options={[
            { id: "single" as const, name: t("setup.rounds.single") },
            { id: "multi" as const, name: t("setup.rounds.multi") },
          ]}
          onChange={(v) => onMultiRound(v === "multi")}
        />
      </div>

      <div className="surface-card p-3.5">
        <div className="grid grid-cols-1 items-end gap-3 lg:grid-cols-[1fr_auto]">
          <ChoiceGroup
            label={t("setup.personality.label")}
            value={config.personality}
            options={options.personalities.map((p) => ({
              id: p.id as InterviewConfig["personality"],
              name: personalityLabel(p.id, t),
            }))}
            onChange={(v) => onConfig({ personality: v as InterviewConfig["personality"] })}
          />
          <div className="lg:w-48">
            <label className="field-label !mb-2 !text-xs">
              {t("setup.strictness.label", {
                n: config.strictness,
                label: t(strictnessLabelKey(config.strictness)),
              })}
            </label>
            <input
              type="range"
              min={1}
              max={10}
              value={config.strictness}
              onChange={(e) => onConfig({ strictness: Number(e.target.value) })}
              className="h-2 w-full accent-[var(--primary)]"
            />
          </div>
        </div>
      </div>

      <div className="surface-card p-3.5">
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
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
          {options.scenes && options.scenes.length > 0 && (
            <Select
              label={t("setup.scene.label")}
              value={config.scene_id || "meeting_room"}
              options={options.scenes.map((s) => s.id)}
              labels={options.scenes.map((s) => sceneLabel(s.id, t))}
              onChange={(v) => onConfig({ scene_id: v })}
            />
          )}
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
        setChatModelId={setChatModelId}
        setSttModelId={setSttModelId}
        setTtsModelId={setTtsModelId}
        setEffort={setEffort}
        defaultBindings={defaultBindings}
        disabled={creating}
      />

      {footer}
    </div>
  );
}
