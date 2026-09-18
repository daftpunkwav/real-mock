/** Capability config view shared by the model form and its zcode-style JSON snippet.
 *
 * The form fields stay canonical: the JSON panel is a projection of the form plus the
 * capability convention keys stored in extras (``reasoning`` / ``modalities``), and
 * "Apply" parses an edited snippet back into form fields + extras. Coercion mirrors
 * the backend backstop in model_registry._normalize_capability_extras. */

import type { ModelDraft } from "./constants";

export const MODALITY_INPUT_VALUES = ["text", "image", "audio", "video", "pdf"];
export const MODALITY_OUTPUT_VALUES = ["text", "audio"];

const REASONING_VARIANTS_MAX = 8;
// Mirrors _MODALITY_TOKEN_MAX in model_registry so a token accepted here is not
// silently truncated again on save.
const TOKEN_MAX_CHARS = 32;

export interface CapabilityConfigView {
  reasoning: { enabled: boolean; variants: string[]; defaultVariant: string };
  limit: { context: number; output: number };
  modalities: { input: string[]; output: string[] };
}

function isObj(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseExtras(text: string): Record<string, unknown> {
  if (!text.trim()) return {};
  try {
    const parsed: unknown = JSON.parse(text);
    return isObj(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function normTokens(value: unknown, allowed: string[] | null, limit: number): string[] {
  if (!Array.isArray(value)) return [];
  const out: string[] = [];
  for (const item of value) {
    const token = String(item ?? "")
      .trim()
      .toLowerCase()
      .slice(0, TOKEN_MAX_CHARS);
    if (!token || out.includes(token) || (allowed && !allowed.includes(token))) continue;
    out.push(token);
    if (out.length >= limit) break;
  }
  return out;
}

function storedVariants(extras: Record<string, unknown>): {
  variants: string[];
  defaultVariant: string;
} {
  const raw = extras.reasoning;
  if (!isObj(raw)) return { variants: [], defaultVariant: "" };
  const variants = normTokens(raw.variants, null, REASONING_VARIANTS_MAX);
  const defaultVariant = String(raw.defaultVariant ?? "")
    .trim()
    .toLowerCase();
  return { variants, defaultVariant: variants.includes(defaultVariant) ? defaultVariant : "" };
}

/** Checkbox-driven modalities (text/image/audio-in/audio-out) win over stored extras;
 * tokens with no checkbox (video/pdf) survive from stored extras only. */
function modalitiesFromDraft(
  draft: ModelDraft,
  stored: Record<string, unknown>,
): { input: string[]; output: string[] } {
  const storedIn = isObj(stored.modalities)
    ? normTokens(stored.modalities.input, MODALITY_INPUT_VALUES, 8)
    : [];
  const input: string[] = [];
  for (const token of MODALITY_INPUT_VALUES) {
    if (token === "text" || token === "image" || token === "audio") {
      const on =
        token === "text" ||
        (token === "image" ? draft.capabilities.vision : draft.capabilities.audio_input);
      if (on) input.push(token);
    } else if (storedIn.includes(token)) {
      input.push(token);
    }
  }
  const output: string[] = [];
  for (const token of MODALITY_OUTPUT_VALUES) {
    const on = token === "text" || (token === "audio" && draft.capabilities.audio_output);
    if (on) output.push(token);
  }
  return { input, output };
}

export function capsConfigFromDraft(draft: ModelDraft): CapabilityConfigView {
  const extras = parseExtras(draft.extras_text);
  const reasoning = storedVariants(extras);
  return {
    reasoning: { enabled: draft.capabilities.reasoning, ...reasoning },
    limit: {
      context: Number(draft.context_window) || 0,
      output: Number(draft.max_output) || 0,
    },
    modalities: modalitiesFromDraft(draft, extras),
  };
}

function toOptionalInt(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

export function applyCapabilityConfig(
  text: string,
  draft: ModelDraft,
): { ok: true; draft: ModelDraft } | { ok: false } {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { ok: false };
  }
  if (!isObj(parsed)) return { ok: false };

  const reasoningRaw = isObj(parsed.reasoning) ? parsed.reasoning : {};
  const variants = normTokens(reasoningRaw.variants, null, REASONING_VARIANTS_MAX);
  const defaultRaw = String(reasoningRaw.defaultVariant ?? "")
    .trim()
    .toLowerCase();
  const defaultVariant = variants.includes(defaultRaw) ? defaultRaw : "";
  const reasoningEnabled = reasoningRaw.enabled === true;

  const limitRaw = isObj(parsed.limit) ? parsed.limit : {};
  const context = toOptionalInt(limitRaw.context);
  const output = toOptionalInt(limitRaw.output);

  const modalRaw = isObj(parsed.modalities) ? parsed.modalities : {};
  const input = normTokens(modalRaw.input, MODALITY_INPUT_VALUES, 8);
  const modalOut = normTokens(modalRaw.output, MODALITY_OUTPUT_VALUES, 4);

  // Replace the convention keys inside extras; unrelated keys (voice credentials,
  // tts_request, …) survive untouched.
  const nextExtras: Record<string, unknown> = { ...parseExtras(draft.extras_text) };
  if (variants.length > 0 || defaultVariant) {
    nextExtras.reasoning = {
      ...(variants.length > 0 ? { variants } : {}),
      ...(defaultVariant ? { defaultVariant } : {}),
    };
  } else {
    delete nextExtras.reasoning;
  }
  if (input.length > 0 || modalOut.length > 0) {
    nextExtras.modalities = {
      ...(input.length > 0 ? { input } : {}),
      ...(modalOut.length > 0 ? { output: modalOut } : {}),
    };
  } else {
    delete nextExtras.modalities;
  }

  const capabilities = { ...draft.capabilities };
  capabilities.reasoning = reasoningEnabled;
  capabilities.vision = input.includes("image");
  capabilities.audio_input = input.includes("audio");
  capabilities.audio_output = modalOut.includes("audio");

  return {
    ok: true,
    draft: {
      ...draft,
      capabilities,
      context_window:
        context !== null && context >= 0 ? String(context) : draft.context_window,
      max_output: output !== null && output >= 1 ? String(output) : draft.max_output,
      extras_text:
        Object.keys(nextExtras).length > 0 ? JSON.stringify(nextExtras, null, 2) : "",
    },
  };
}
