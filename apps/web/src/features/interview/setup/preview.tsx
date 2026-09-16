"use client";

/** Interview setup preview: config summary + agent-researched company brief. */

import { useCallback, useEffect, useRef, useState } from "react";
import { useLocale, useT } from "@/i18n";
import {
  Briefcase,
  Building2,
  FileText,
  ListChecks,
  Mic,
  RefreshCw,
  UserCircle,
  Video,
} from "lucide-react";
import type { InterviewConfig, Options, ResumePickerItem } from "@/lib/api/contract";
import type { CompanyBrief } from "@/types";
import { interviewHttp } from "@/lib/api/interviewHttp";
import { strictnessLabelKey } from "./fields";
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
} from "./optionLabels";

/** Debounce before fetching/generating: merges keystrokes on custom fields. */
const BRIEF_DEBOUNCE_MS = 600;

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

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1 text-[10px] uppercase tracking-[0.08em] text-ink-subtle">{children}</p>
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
  const presetCompanyName = selectedCompanyRaw ? companyDisplay(selectedCompanyRaw, t).name : null;
  // Preset companies carry their catalog id; custom companies carry the typed name.
  const companyName = (presetCompanyName ?? config.company.trim()) || null;
  const selectedAvatar = options.avatars?.find((a) => a.id === config.avatar_id);
  const selectedScene = options.scenes?.find((s) => s.id === config.scene_id);
  const selectedResume = resumes.find((r) => r.id === config.resume_id);

  const roleDisplay = isPresetRole(config.role, options.roles)
    ? roleLabel(config.role, t)
    : config.role.trim() || t("setup.role.custom");
  const levelDisplay = levelLabel(config.level, t);

  const avatarSceneValue = [
    selectedAvatar ? avatarLabel(selectedAvatar.id, locale) : null,
    selectedAvatar?.voice
      ? t("preview.voice", { name: voiceLabel(selectedAvatar.voice, t) })
      : null,
    selectedScene ? sceneLabel(selectedScene.id, t) : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const [brief, setBrief] = useState<CompanyBrief | null>(null);
  const [briefLoading, setBriefLoading] = useState(false);
  const [briefError, setBriefError] = useState(false);
  // Only the latest request may update state; StrictMode double-mounts (and any
  // retry while one is in flight) would otherwise interleave stale outcomes.
  const briefReqSeq = useRef(0);

  const loadBrief = useCallback(
    async (signal?: AbortSignal) => {
      if (!companyName) return;
      const seq = ++briefReqSeq.current;
      setBriefLoading(true);
      setBriefError(false);
      try {
        const res = await interviewHttp.fetchCompanyBrief(
          companyName,
          roleDisplay,
          levelDisplay,
          config.workflow_type,
          { signal, locale },
        );
        if (seq !== briefReqSeq.current) return;
        setBrief(res);
        setBriefError(false);
      } catch {
        // The seq guard also covers aborts: a cancelled request is always
        // superseded by a newer one (or by unmount), so it never touches state.
        if (seq !== briefReqSeq.current) return;
        setBrief(null);
        setBriefError(true);
      } finally {
        if (seq === briefReqSeq.current) setBriefLoading(false);
      }
    },
    // Any setup field (or UI language) that scopes the brief must re-trigger the fetch.
    [companyName, roleDisplay, levelDisplay, config.workflow_type, locale],
  );

  useEffect(() => {
    setBrief(null);
    setBriefError(false);
    // Debounce + cancel: custom company/role inputs fire per keystroke and every
    // keystroke is a cache miss that would otherwise start a full LLM research.
    const controller = new AbortController();
    const timer = setTimeout(() => void loadBrief(controller.signal), BRIEF_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      briefReqSeq.current += 1; // invalidate any late outcome, aborted or not
      controller.abort();
    };
  }, [loadBrief]);

  return (
    <div className="flex h-full flex-col gap-2.5 overflow-hidden">
      <div className="surface-card shrink-0 p-3.5">
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
            value={companyName ?? config.company}
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
          {avatarSceneValue && (
            <PreviewRow icon={Video} label={t("preview.row.avatar")} value={avatarSceneValue} />
          )}
          <PreviewRow
            icon={FileText}
            label={t("preview.row.resume")}
            value={selectedResume ? selectedResume.filename : t("preview.row.resumeEmpty")}
          />
        </div>
      </div>

      {companyName && (
        <div className="surface-card min-h-0 flex-1 overflow-y-auto p-3.5">
          <h2 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-ink">
            <Building2 size={14} className="text-[var(--primary)]" />
            {t("preview.companyQuestions", { name: companyName })}
          </h2>

          {briefLoading && (
            <p className="flex items-center gap-2 py-4 text-[11px] text-ink-muted">
              <RefreshCw size={13} className="anim-spin text-[var(--primary)]" />
              {t("preview.brief.loading", { name: companyName })}
            </p>
          )}

          {!briefLoading && briefError && (
            <div className="py-3 text-center">
              <p className="mb-2 text-[11px] leading-snug text-[var(--warning-ink)]">
                {t("preview.brief.error")}
              </p>
              <button
                type="button"
                className="rounded-md border border-surface-border px-3 py-1.5 text-[11px] text-ink-muted transition-colors hover:border-[var(--primary)] hover:text-ink"
                onClick={() => void loadBrief()}
              >
                {t("preview.brief.retry")}
              </button>
            </div>
          )}

          {!briefLoading && brief && (
            <>
              <SectionLabel>{t("preview.style")}</SectionLabel>
              <p className="mb-2.5 text-[11px] leading-snug text-ink-muted">{brief.style}</p>

              {brief.focus_areas.length > 0 && (
                <>
                  <SectionLabel>{t("preview.focus")}</SectionLabel>
                  <div className="mb-1 flex flex-wrap gap-1">
                    {brief.focus_areas.map((area) => (
                      <span key={area} className="chip chip-blue !text-[10px]">
                        {area}
                      </span>
                    ))}
                  </div>
                </>
              )}

              <div className="my-2.5 border-t border-surface-border" />

              <SectionLabel>{t("preview.process")}</SectionLabel>
              <p className="mb-2 text-[11px] leading-snug text-ink-muted">{brief.process}</p>
            </>
          )}

          {!selectedResume && (
            <p className="rounded-md border border-[var(--warning)]/30 bg-[var(--warning-soft)] px-2 py-1.5 text-[11px] leading-snug text-[var(--warning-ink)]">
              {t("preview.flow.noResume")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
