/**
 * @file askDialog.ts
 * @description Pure ask_user dialog helpers: SSE event normalization and
 * answer-text formatting. No React, no I/O — safe for unit tests and reuse.
 */

import type { AskUserDialog, AskUserScale, AskUserSelection, AskUserWidget } from "@/types";

/** Backend option cap mirrored client-side (defense in depth). */
export const ASK_MAX_OPTIONS = 8;

/** Backend question-per-dialog cap mirrored client-side (defense in depth). */
export const ASK_MAX_QUESTIONS = 8;

function asSelection(raw: unknown): AskUserSelection {
  return raw === "multi" ? "multi" : "single";
}

function asWidget(raw: unknown): AskUserWidget {
  return raw === "slider" || raw === "rating" ? raw : "options";
}

function asFiniteNumber(raw: unknown): number | undefined {
  if (typeof raw === "boolean") return undefined;
  const n = Number(raw);
  return Number.isFinite(n) ? n : undefined;
}

function asScale(raw: unknown): AskUserScale | undefined {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return undefined;
  const src = raw as Record<string, unknown>;
  const scale: AskUserScale = {};
  for (const key of ["min", "max", "step"] as const) {
    const n = asFiniteNumber(src[key]);
    if (n !== undefined) scale[key] = n;
  }
  if (typeof src.unit === "string" && src.unit.trim()) scale.unit = src.unit.trim().slice(0, 12);
  return Object.keys(scale).length > 0 ? scale : undefined;
}

function asAllowCustom(raw: unknown): boolean {
  if (typeof raw === "string") {
    return !["false", "no", "off", "0"].includes(raw.trim().toLowerCase());
  }
  return raw === false || raw === 0 ? false : true;
}

/** Clamp a raw SSE ask_user event into a renderable dialog (backend already validates; stay defensive). */
export function normalizeAskDialog(raw: {
  question: unknown;
  options: unknown;
  selection?: unknown;
  widget?: unknown;
  scale?: unknown;
  allow_custom?: unknown;
  suggested?: unknown;
  questions?: unknown;
}): AskUserDialog {
  // Dedupe (order kept): repeated labels collide as dialog keys.
  const options = [...new Set(
    (Array.isArray(raw.options) ? raw.options : [])
      .map(String)
      .map((s) => s.trim())
      .filter(Boolean),
  )].slice(0, ASK_MAX_OPTIONS);
  let widget = asWidget(raw.widget);
  const scale = asScale(raw.scale);
  if (widget === "slider" && (scale?.min === undefined || scale?.max === undefined || !(scale.min < scale.max))) {
    // Unusable slider range: degrade to the options list, mirroring the backend.
    widget = "options";
  }
  const dialog: AskUserDialog = {
    question: String(raw.question ?? ""),
    options,
    selection: asSelection(raw.selection),
    widget,
    scale,
    allow_custom: asAllowCustom(raw.allow_custom),
    suggested: typeof raw.suggested === "string" && raw.suggested ? raw.suggested : null,
  };
  // Multi-question dialogs: normalize each entry with the same rules. The flat
  // fields mirror questions[0] (backend contract), so only the array is new.
  const rawQuestions = Array.isArray(raw.questions) ? raw.questions : [];
  const questions = rawQuestions
    .filter((q): q is Record<string, unknown> => !!q && typeof q === "object")
    .slice(0, ASK_MAX_QUESTIONS)
    .map((q) => normalizeAskDialog(q as Parameters<typeof normalizeAskDialog>[0]));
  if (questions.length > 1) dialog.questions = questions;
  return dialog;
}

/** Format a slider numeric value: drop the trailing .0, keep the unit. */
export function formatSliderValue(value: string, unit: string): string {
  const n = Number(value);
  const body = Number.isFinite(n) && Number.isInteger(n) ? String(n) : value;
  return `${body}${unit}`;
}

/** Assemble the user-visible answer text sent back to the agent. */
export function formatAskAnswer(
  dialog: Pick<AskUserDialog, "widget" | "scale">,
  value: { options?: string[]; slider?: string; rating?: number },
): string {
  if (value.slider !== undefined) {
    return formatSliderValue(value.slider, dialog.scale?.unit ?? "");
  }
  if (value.rating !== undefined) {
    const max = dialog.scale?.max ?? 5;
    return `${value.rating}/${max}`;
  }
  return (value.options ?? []).join("、");
}
