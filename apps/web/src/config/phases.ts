/**
 * Interview phase English labels (SSOT lock + offline reference).
 *
 * Authoritative source: backend ``workflows.py`` (PhaseDef).
 * ``test_phase_ssot.py`` asserts these English strings match the backend.
 *
 * **Do not use this map directly for UI** — use ``resolvePhaseLabels()`` /
 * ``interview.phase.*`` i18n so Chinese UI stays localized.
 * options API ``phase_labels`` only fills unknown ids not registered here.
 */
import type { LocaleId } from "@/i18n/locales";
import { createTranslator, getLocale } from "@/i18n/resolve";

export const PHASE_LABELS: Record<string, string> = {
  identity_check: "Identity check",
  self_intro: "Self introduction",
  basic_knowledge: "Fundamentals",
  project_deep_dive: "Project deep dive",
  technical_deep: "Technical deep dive",
  system_design: "System design",
  scenario: "Scenario questions",
  reverse_qa: "Your questions",
  summary: "Summary",
  // HR / management (also shipped via options; keep local to avoid flicker)
  career_plan: "Career plans",
  teamwork: "Teamwork",
  pressure: "Pressure questions",
  salary: "Compensation",
  leadership: "Leadership",
  decision_making: "Decision making",
  conflict: "Conflict handling",
  business: "Business sense",
} as const;

/** Resolve phase display names for a UI locale; known ids prefer i18n. */
export function resolvePhaseLabels(
  overlay?: Record<string, string> | null,
  /** React callers pass locale for memo deps; defaults to non-React current */
  locale: LocaleId = getLocale(),
): Record<string, string> {
  const t = createTranslator(locale, "interview");
  const out: Record<string, string> = {};
  for (const id of Object.keys(PHASE_LABELS)) {
    out[id] = t(`phase.${id}`);
  }
  if (overlay) {
    for (const [id, label] of Object.entries(overlay)) {
      if (!(id in out) && label) out[id] = label;
    }
  }
  return out;
}

/** Technical workflow default order (matches ``technical_phase_order()``). */
export const PHASE_ORDER: readonly string[] = [
  "identity_check",
  "self_intro",
  "basic_knowledge",
  "project_deep_dive",
  "technical_deep",
  "system_design",
  "scenario",
  "reverse_qa",
  "summary",
] as const;
