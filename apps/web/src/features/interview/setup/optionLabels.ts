/**
 * Localized display helpers for interview setup option catalogs.
 *
 * Backend catalogs expose stable ids (and English fallback names). UI must
 * always prefer ``interview.options.*`` / ``media.avatar.profile.*`` keys.
 */

import { createTranslator, getLocale, type Translator } from "@/i18n/resolve";
import type { LocaleId } from "@/i18n/locales";
import type { CompanyInfo, Options } from "@/lib/api/contract";
import { resolvePhaseLabels } from "@/config/phases";

/** Sentinel select value for free-form job title (not a backend role id). */
export const CUSTOM_ROLE_ID = "custom";

type InterviewT = Translator<"interview">;

function pick(t: InterviewT, key: string, fallback: string): string {
  return t.has(key) ? t(key) : fallback;
}

export function roleLabel(id: string, t: InterviewT): string {
  if (id === CUSTOM_ROLE_ID) return t("setup.role.custom");
  return pick(t, `options.role.${id}`, id);
}

export function levelLabel(id: string, t: InterviewT): string {
  return pick(t, `options.level.${id}`, id);
}

export function personalityLabel(id: string, t: InterviewT): string {
  return pick(t, `options.personality.${id}`, id);
}

export function styleLabel(id: string, t: InterviewT): string {
  return pick(t, `options.style.${id}`, id);
}

export function workflowLabel(id: string, t: InterviewT): string {
  return pick(t, `options.workflow.${id}`, id);
}

export function sceneLabel(id: string, t: InterviewT): string {
  return pick(t, `options.scene.${id}`, id);
}

/** Prefer media namespace avatar labels (single source with room avatar UI). */
export function avatarLabel(id: string, locale: LocaleId = getLocale()): string {
  const mediaT = createTranslator(locale, "media");
  const key = `avatar.profile.${id}`;
  return mediaT.has(key) ? mediaT(key) : id;
}

export function voiceLabel(id: string, t: InterviewT): string {
  return pick(t, `options.voice.${id}`, id);
}

export type CompanyDisplay = {
  id: string;
  name: string;
  style: string;
  focusAreas: string[];
  sample0: string;
};

export function companyDisplay(company: CompanyInfo, t: InterviewT): CompanyDisplay {
  const base = `options.company.${company.id}`;
  const focusRaw = pick(t, `${base}.focus`, company.focus_areas.join("|"));
  const focusAreas = focusRaw
    .split("|")
    .map((s) => s.trim())
    .filter(Boolean);
  return {
    id: company.id,
    name: pick(t, `${base}.name`, company.name),
    style: pick(t, `${base}.style`, company.style),
    focusAreas: focusAreas.length > 0 ? focusAreas : company.focus_areas,
    sample0: pick(t, `${base}.sample0`, company.sample_questions[0] ?? ""),
  };
}

/** True when ``role`` is a catalog preset id (not free-form custom text). */
export function isPresetRole(role: string, roleIds: readonly string[]): boolean {
  return roleIds.includes(role);
}

/**
 * Resolve role/level ids to localized human-readable labels for createSession.
 * Custom free-form role text is passed through unchanged.
 */
export function resolveConfigLabelsForApi(
  role: string,
  level: string,
  roleIds: readonly string[],
  t: InterviewT,
): { role: string; level: string } {
  return {
    role: isPresetRole(role, roleIds) ? roleLabel(role, t) : role.trim(),
    level: levelLabel(level, t),
  };
}

export type LocalizedOptionsView = {
  roleIds: string[];
  roleLabels: string[];
  levelLabels: string[];
  workflowLabels: Record<string, string>;
  styleLabels: Record<string, string>;
  personalityLabels: Record<string, string>;
  sceneLabels: Record<string, string>;
  companies: CompanyDisplay[];
  phaseLabels: Record<string, string>;
};

export function localizeOptions(
  options: Options,
  t: InterviewT,
  locale: LocaleId = getLocale(),
): LocalizedOptionsView {
  const phaseLabels = resolvePhaseLabels(options.phase_labels, locale);
  return {
    roleIds: options.roles,
    roleLabels: options.roles.map((id) => roleLabel(id, t)),
    levelLabels: options.levels.map((id) => levelLabel(id, t)),
    workflowLabels: Object.fromEntries(
      options.workflow_types.map((w) => [w.id, workflowLabel(w.id, t)]),
    ),
    styleLabels: Object.fromEntries(
      options.interview_styles.map((s) => [s.id, styleLabel(s.id, t)]),
    ),
    personalityLabels: Object.fromEntries(
      options.personalities.map((p) => [p.id, personalityLabel(p.id, t)]),
    ),
    sceneLabels: Object.fromEntries(
      (options.scenes ?? []).map((s) => [s.id, sceneLabel(s.id, t)]),
    ),
    companies: options.companies.map((c) => companyDisplay(c, t)),
    phaseLabels,
  };
}

/** Map workflow phase ids to localized labels for the preview process line. */
export function workflowProcessLine(
  phaseIds: readonly string[],
  phaseLabels: Record<string, string>,
): string {
  return phaseIds.map((id) => phaseLabels[id] || id).join(" → ");
}
