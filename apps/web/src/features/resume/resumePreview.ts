/**
 * @file resumePreview
 * @description Pure helpers for the sticky resume preview card.
 *
 * Responsibilities:
 * - Shorten skill chips without inventing labels
 *
 * Must not import React.
 */

import type { ParsedProject } from "./resumeNormalize";
import { PREVIEW_SKILL_CHARS } from "./resumeLimits";

/** First `::` / `:` segment when it is a real label; otherwise the trimmed skill. */
export function shortSkillLabel(skill: string, maxChars = PREVIEW_SKILL_CHARS): string {
  const head = (skill.split(/[::]/, 1)[0] ?? "").trim();
  const base = head.length >= 2 && head.length < skill.length ? head : skill.trim();
  return base.length > maxChars ? `${base.slice(0, maxChars)}…` : base;
}

/** Content keys survive reordering; a per-content count distinguishes exact duplicates. */
export function keyedPreviewProjects(projects: ParsedProject[]) {
  const occurrences = new Map<string, number>();
  return projects.map((project) => {
    const content = JSON.stringify(Object.entries(project).sort(([a], [b]) => a.localeCompare(b)));
    const occurrence = occurrences.get(content) ?? 0;
    occurrences.set(content, occurrence + 1);
    return { project, key: JSON.stringify([content, occurrence]) };
  });
}
