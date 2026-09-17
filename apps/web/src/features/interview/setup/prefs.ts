/**
 * Interview setup preference persistence (localStorage-backed).
 *
 * The setup page restores the visitor's last configuration (role, level,
 * company, format, presenter, processor bindings) so a refresh or re-entry
 * keeps every previous choice. Stored values are untrusted: reads only accept
 * well-formed payloads, and option-dependent fields are validated against the
 * live catalogs at restore time, falling back to the built-in defaults.
 */

import type { InterviewConfig, Options, ResumePickerItem } from "@/lib/api/contract";
import type { ReasoningEffort, ReferenceDetail } from "@/types";

/** localStorage key holding the whole setup preference blob. */
export const SETUP_PREFS_KEY = "realmock_interview_setup_prefs";

const EFFORT_VALUES: readonly string[] = ["low", "medium", "high", "max"];
const REFERENCE_DETAIL_VALUES: readonly string[] = ["outline", "full"];
const MODEL_ID_KEYS = ["chatModelId", "sttModelId", "ttsModelId"] as const;

/** Persisted setup preferences; every field is optional and untrusted. */
export interface StoredSetupPrefs {
  config?: Partial<InterviewConfig>;
  multiRound?: boolean;
  chatModelId?: number | null;
  sttModelId?: number | null;
  ttsModelId?: number | null;
  effort?: ReasoningEffort;
  referenceDetail?: ReferenceDetail;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isModelId(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

/** Read stored prefs; malformed or foreign payloads yield an empty object. */
export function readSetupPrefs(): StoredSetupPrefs {
  try {
    if (typeof window === "undefined" || !window.localStorage) return {};
    const raw = window.localStorage.getItem(SETUP_PREFS_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed)) return {};

    const prefs: StoredSetupPrefs = {};
    if (isRecord(parsed.config)) prefs.config = parsed.config as Partial<InterviewConfig>;
    if (typeof parsed.multiRound === "boolean") prefs.multiRound = parsed.multiRound;
    for (const key of MODEL_ID_KEYS) {
      if (isModelId(parsed[key])) prefs[key] = parsed[key] as number | null;
    }
    if (typeof parsed.effort === "string" && EFFORT_VALUES.includes(parsed.effort)) {
      prefs.effort = parsed.effort as ReasoningEffort;
    }
    if (
      typeof parsed.referenceDetail === "string" &&
      REFERENCE_DETAIL_VALUES.includes(parsed.referenceDetail)
    ) {
      prefs.referenceDetail = parsed.referenceDetail as ReferenceDetail;
    }
    return prefs;
  } catch {
    return {};
  }
}

/** Persist the full preference set; storage failures are non-fatal. */
export function writeSetupPrefs(prefs: StoredSetupPrefs): void {
  try {
    window.localStorage.setItem(SETUP_PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // Non-fatal: the defaults apply next load.
  }
}

/**
 * Validate stored config fields against the live option catalogs and return
 * the patch to merge into the current config. Fields failing validation are
 * omitted so the built-in default (or the active-resume fallback) applies.
 * Free-form custom role/company text is kept when non-blank; preset ids must
 * still exist in the catalog.
 */
export function restoreSetupConfig(
  stored: Partial<InterviewConfig> | undefined,
  options: Options,
  resumes: ResumePickerItem[],
): Partial<InterviewConfig> {
  if (!isRecord(stored)) return {};
  const patch: Partial<InterviewConfig> = {};

  if (typeof stored.role === "string" && (options.roles.includes(stored.role) || stored.role.trim())) {
    patch.role = stored.role;
  }
  if (typeof stored.level === "string" && options.levels.includes(stored.level)) {
    patch.level = stored.level;
  }
  if (
    typeof stored.company === "string" &&
    (options.companies.some((c) => c.id === stored.company) || stored.company.trim())
  ) {
    patch.company = stored.company;
  }
  if (options.workflow_types.some((w) => w.id === stored.workflow_type)) {
    patch.workflow_type = stored.workflow_type;
  }
  if (options.interview_styles.some((s) => s.id === stored.interview_style)) {
    patch.interview_style = stored.interview_style;
  }
  if (options.personalities.some((p) => p.id === stored.personality)) {
    patch.personality = stored.personality;
  }
  if (
    typeof stored.strictness === "number" &&
    Number.isInteger(stored.strictness) &&
    stored.strictness >= 1 &&
    stored.strictness <= 10
  ) {
    patch.strictness = stored.strictness;
  }
  if ((options.avatars ?? []).some((a) => a.id === stored.avatar_id)) {
    patch.avatar_id = stored.avatar_id;
  }
  if ((options.scenes ?? []).some((s) => s.id === stored.scene_id)) {
    patch.scene_id = stored.scene_id;
  }
  if (typeof stored.resume_id === "number" && resumes.some((r) => r.id === stored.resume_id)) {
    patch.resume_id = stored.resume_id;
  }
  return patch;
}

/** Stored model id is kept only when it still exists in the capability bucket. */
export function restoreModelId(
  stored: number | null | undefined,
  models: readonly { id: number }[],
): number | null {
  if (typeof stored !== "number") return null;
  return models.some((m) => m.id === stored) ? stored : null;
}
