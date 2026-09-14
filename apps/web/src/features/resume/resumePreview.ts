/**
 * @file resumePreview
 * @description Pure helpers for the sticky resume preview card.
 *
 * Responsibilities:
 * - Shorten skill chips without inventing labels
 *
 * Must not import React.
 */

import { PREVIEW_SKILL_CHARS } from "./resumeLimits";

/** First `::` / `:` segment when it is a real label; otherwise the trimmed skill. */
export function shortSkillLabel(skill: string, maxChars = PREVIEW_SKILL_CHARS): string {
  const head = (skill.split(/[::]/, 1)[0] ?? "").trim();
  const base = head.length >= 2 && head.length < skill.length ? head : skill.trim();
  return base.length > maxChars ? `${base.slice(0, maxChars)}…` : base;
}
