/**
 * @file compactThreshold.ts
 * @description Prep compaction preferences (localStorage-backed): auto-compact
 * trigger, compression intensity, compression directive, and the verbatim
 * retain window. Every send resolves these fresh so settings changes apply
 * without reload; the backend re-validates everything it receives.
 */

export type CompactThresholdSetting = "auto" | 0.5 | 0.6 | 0.7 | 0.8 | 0.9;

/** localStorage key for the auto-compact threshold setting. */
export const COMPACT_THRESHOLD_KEY = "realmock_prep_compact_threshold";

/** Default: the agent decides when to compact. */
export const COMPACT_THRESHOLD_DEFAULT: CompactThresholdSetting = "auto";

/** Selectable thresholds in the settings UI. */
export const COMPACT_THRESHOLD_OPTIONS: CompactThresholdSetting[] = [
  "auto",
  0.5,
  0.6,
  0.7,
  0.8,
  0.9,
];

/** Read the configured threshold; falls back to "auto" on any anomaly. */
export function readCompactThreshold(): CompactThresholdSetting {
  try {
    if (typeof window === "undefined" || !window.localStorage)
      return COMPACT_THRESHOLD_DEFAULT;
    const raw = window.localStorage.getItem(COMPACT_THRESHOLD_KEY);
    if (raw === null) return COMPACT_THRESHOLD_DEFAULT;
    if (raw === "auto") return "auto";
    const value = Number(raw);
    return (COMPACT_THRESHOLD_OPTIONS as (string | number)[]).includes(value)
      ? (value as CompactThresholdSetting)
      : COMPACT_THRESHOLD_DEFAULT;
  } catch {
    return COMPACT_THRESHOLD_DEFAULT;
  }
}

/** Persist the threshold; ignores storage failures (private-mode browsers). */
export function writeCompactThreshold(value: CompactThresholdSetting): void {
  try {
    window.localStorage.setItem(COMPACT_THRESHOLD_KEY, String(value));
  } catch {
    // Non-fatal: the default applies next load.
  }
}

/**
 * Map the UI setting to the request payload: "auto" sends nothing (the
 * backend uses its agent-decided default), a number sends the fraction.
 */
export function toCompactThresholdParam(
  value: CompactThresholdSetting,
): number | undefined {
  return value === "auto" ? undefined : value;
}

/** Compression intensity levels (shared vocabulary with the backend). */
export type CompactionIntensity = "light" | "balanced" | "aggressive";

/** localStorage keys for the remaining compaction preferences. */
export const COMPACT_INTENSITY_KEY = "realmock_prep_compact_intensity";
export const COMPACT_DIRECTIVE_KEY = "realmock_prep_compact_directive";
export const COMPACT_RETAIN_KEY = "realmock_prep_compact_retain";

/** Default intensity: standard window with standard summary detail. */
export const COMPACT_INTENSITY_DEFAULT: CompactionIntensity = "balanced";

/** Selectable intensities in the settings UI. */
export const COMPACT_INTENSITY_OPTIONS: CompactionIntensity[] = [
  "light",
  "balanced",
  "aggressive",
];

/** Default verbatim tail (recent messages exempt from compaction). */
export const COMPACT_RETAIN_DEFAULT = 4;

/** Retain window bounds (mirrors the backend 422 envelope). */
export const COMPACT_RETAIN_MIN = 0;
export const COMPACT_RETAIN_MAX = 200;

/** Max stored directive characters (mirrors the backend limit). */
export const COMPACT_DIRECTIVE_MAX_CHARS = 500;

function readStored(key: string): string | null {
  try {
    if (typeof window === "undefined" || !window.localStorage) return null;
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Non-fatal: the default applies next load.
  }
}

/** Read the compression intensity; falls back to balanced on any anomaly. */
export function readCompactIntensity(): CompactionIntensity {
  const raw = readStored(COMPACT_INTENSITY_KEY);
  return (COMPACT_INTENSITY_OPTIONS as string[]).includes(raw ?? "")
    ? (raw as CompactionIntensity)
    : COMPACT_INTENSITY_DEFAULT;
}

/** Persist the compression intensity. */
export function writeCompactIntensity(value: CompactionIntensity): void {
  writeStored(
    COMPACT_INTENSITY_KEY,
    (COMPACT_INTENSITY_OPTIONS as string[]).includes(value) ? value : COMPACT_INTENSITY_DEFAULT,
  );
}

/** Read the compression directive (free text, trimmed and bounded). */
export function readCompactDirective(): string {
  const raw = readStored(COMPACT_DIRECTIVE_KEY) ?? "";
  return raw.trim().slice(0, COMPACT_DIRECTIVE_MAX_CHARS);
}

/** Persist the compression directive (trimmed and bounded). */
export function writeCompactDirective(value: string): void {
  writeStored(COMPACT_DIRECTIVE_KEY, (value ?? "").trim().slice(0, COMPACT_DIRECTIVE_MAX_CHARS));
}

/**
 * Read the verbatim retain window (recent messages exempt from compaction).
 * Non-negative integer; garbage and negatives fall back to the default so an
 * invalid stored value can never widen or disable compaction silently.
 */
export function readCompactRetain(): number {
  const raw = readStored(COMPACT_RETAIN_KEY);
  if (raw === null) return COMPACT_RETAIN_DEFAULT;
  const parsed = Number(raw);
  if (!Number.isInteger(parsed) || parsed < COMPACT_RETAIN_MIN) return COMPACT_RETAIN_DEFAULT;
  return Math.min(parsed, COMPACT_RETAIN_MAX);
}

/** Persist the retain window (clamped to the valid range). */
export function writeCompactRetain(value: number): void {
  const parsed = Number(value);
  const valid =
    Number.isInteger(parsed) && parsed >= COMPACT_RETAIN_MIN
      ? Math.min(parsed, COMPACT_RETAIN_MAX)
      : COMPACT_RETAIN_DEFAULT;
  writeStored(COMPACT_RETAIN_KEY, String(valid));
}

/** Resolved per-turn compaction parameters for request payloads. */
export interface ResolvedCompactParams {
  intensity: CompactionIntensity;
  directive?: string;
  retain: number;
}

/** Resolve all compaction preferences fresh (settings apply without reload). */
export function resolveCompactParams(): ResolvedCompactParams {
  const directive = readCompactDirective();
  return {
    intensity: readCompactIntensity(),
    ...(directive ? { directive } : {}),
    retain: readCompactRetain(),
  };
}
