"use client";

/** Interview setup preview: config summary + company insights + tip. */

import { useLocale, useT } from "@/i18n";
import { Briefcase, Building2, Lightbulb, ListChecks, Mic, UserCircle } from "lucide-react";
import type { InterviewConfig, Options, ResumePickerItem } from "@/lib/api/contract";
import { strictnessLabelKey } from "./form";
import {
  avatarLabel,
  companyDisplay,
  isPresetRole,
  levelLabel,
  personalityLabel,
  roleLabel,
  sceneLabel,
  styleLabel,
  voiceLabel,
  workflowLabel,
  workflowProcessLine,
} from "./optionLabels";
import { resolvePhaseLabels } from "@/config/phases";

export function PreviewRow({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ size?: number; className?: string; strokeWidth?: number }>;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-1.5">
      <Icon size={12} className="mt-0.5 shrink-0 text-ink-subtle" strokeWidth={1.75} />
      <div className="min-w-0">
        <span className="text-[10px] uppercase tracking-[0.08em] text-ink-subtle">{label}</span>
        <p className="break-words text-[12px] font-medium leading-snug text-ink">{value}</p>
      </div>
    </div>
  );
}

export function InterviewPreview({
  options,
  config,
  resumes,
}: {
  options: Options;
  config: InterviewConfig;
  resumes: ResumePickerItem[];
}) {
  const t = useT("interview");
  const { locale } = useLocale();
  const selectedCompanyRaw = options.companies.find((c) => c.id === config.company);
  const selectedCompany = selectedCompanyRaw ? companyDisplay(selectedCompanyRaw, t) : null;
  const selectedWorkflow = options.workflow_types.find((w) => w.id === config.workflow_type);
  const selectedAvatar = options.avatars?.find((a) => a.id === config.avatar_id);
  const selectedScene = options.scenes?.find((s) => s.id === config.scene_id);
  const selectedResume = resumes.find((r) => r.id === config.resume_id);
  const phaseLabels = resolvePhaseLabels(options.phase_labels, locale);

  const roleDisplay = isPresetRole(config.role, options.roles)
    ? roleLabel(config.role, t)
    : config.role.trim() || t("setup.role.custom");
  const levelDisplay = levelLabel(config.level, t);

  return (
    <div className="flex h-full flex-col gap-2.5 overflow-hidden">
      <div className="surface-card p-3.5">
        <h2 className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold text-ink">
          <ListChecks size={14} className="text-[var(--primary)]" />
          {t("preview.title")}
        </h2>
        <div className="space-y-2 text-xs">
          <PreviewRow
            icon={Briefcase}
            label={t("preview.row.role")}
            value={`${roleDisplay} · ${levelDisplay}`}
          />
          <PreviewRow
            icon={Building2}
            label={t("preview.row.company")}
            value={selectedCompany?.name ?? config.company}
          />
          <PreviewRow
            icon={Mic}
            label={t("preview.row.type")}
            value={`${workflowLabel(config.workflow_type, t)} · ${styleLabel(config.interview_style, t)}`}
          />
          <PreviewRow
            icon={UserCircle}
            label={t("preview.row.interviewer")}
            value={`${personalityLabel(config.personality, t)} · ${t(strictnessLabelKey(config.strictness))}`}
          />
          {(selectedAvatar || selectedScene) && (
            <PreviewRow
              icon={UserCircle}
              label={t("preview.row.avatar")}
              value={[
                selectedAvatar ? avatarLabel(selectedAvatar.id, locale) : null,
                selectedAvatar?.voice
                  ? t("preview.voice", { name: voiceLabel(selectedAvatar.voice, t) })
                  : null,
                selectedScene ? sceneLabel(selectedScene.id, t) : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            />
          )}
          {selectedResume && (
            <PreviewRow icon={Briefcase} label={t("preview.row.resume")} value={selectedResume.filename} />
          )}
        </div>
      </div>

      {selectedCompany && (
        <div className="surface-card min-h-0 flex-1 overflow-y-auto p-3.5">
          <h2 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-ink">
            <Building2 size={14} className="text-[var(--primary)]" />
            {t("preview.companyQuestions", { name: selectedCompany.name })}
          </h2>
          <p className="mb-2 line-clamp-3 text-[11px] leading-snug text-ink-muted">
            {selectedCompany.style}
          </p>
          {selectedCompany.focusAreas.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1">
              {selectedCompany.focusAreas.slice(0, 6).map((area) => (
                <span key={area} className="chip chip-blue !text-[10px]">
                  {area}
                </span>
              ))}
            </div>
          )}
          {selectedWorkflow && selectedWorkflow.phases.length > 0 && (
            <div className="mb-2">
              <p className="mb-1 text-[10px] uppercase tracking-[0.08em] text-ink-subtle">
                {t("preview.process")}
              </p>
              <p className="font-mono text-[11px] leading-snug text-ink-muted">
                {workflowProcessLine(selectedWorkflow.phases, phaseLabels)}
              </p>
            </div>
          )}
          {selectedCompany.sample0 && (
            <p className="line-clamp-3 text-[11px] leading-snug text-ink-muted">
              <span className="text-ink-subtle">{t("preview.samplePrefix")}</span>
              {selectedCompany.sample0}
            </p>
          )}
        </div>
      )}

      <div className="surface-card shrink-0 px-3.5 py-2.5">
        <p className="flex items-start gap-1.5 text-[11px] leading-snug text-ink-muted">
          <Lightbulb size={13} className="mt-0.5 shrink-0 text-[var(--primary)]" />
          {t("preview.tip")}
        </p>
      </div>
    </div>
  );
}
