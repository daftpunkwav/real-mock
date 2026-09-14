/**
 * @file sessionRefs.ts
 * @description Per-turn "#" session references: pure matching helpers.
 * References attach session history to one turn only (transient backend
 * injection); they never persist as links. UI-free and unit-testable.
 */

import type { PrepSessionSummary } from "@/lib/api/contract";

/** A session chip pending attachment to the next send. */
export interface PendingSessionRef {
  id: number;
  label: string;
}

/** Short chip label: summary, filename, or a fallback. */
export function refLabel(
  s: Pick<PrepSessionSummary, "summary" | "resume_filename">,
  fallback: string,
): string {
  const text = (s.summary || s.resume_filename || "").trim();
  return text || fallback;
}

/**
 * Detect a trailing "#query" token (the "#" starts the token: preceded by
 * start or whitespace, no spaces after). Mid-input "#" tokens are ignored.
 */
export function detectHashQuery(input: string): { query: string } | null {
  const match = /(?:^|\s)#([^\s#]*)$/.exec(input);
  if (!match) return null;
  return { query: match[1] ?? "" };
}

/** Remove the trailing "#query" token after a chip is picked. */
export function stripHashQuery(input: string): string {
  return input.replace(/(?:^|\s)#[^\s#]*$/, (m) => (m.startsWith(" ") ? " " : "")).trimEnd();
}

/** Candidate sessions for the "#" menu: excludes current + picked, caps at 8. */
export function refCandidates(
  sessions: PrepSessionSummary[],
  currentId: number | null,
  pickedIds: readonly number[],
  query: string,
  fallback: string,
): PendingSessionRef[] {
  const picked = new Set(pickedIds);
  const needle = query.trim().toLowerCase();
  const out: PendingSessionRef[] = [];
  for (const s of sessions) {
    if (s.id === currentId || picked.has(s.id)) continue;
    const label = refLabel(s, fallback);
    if (needle && !`${label} ${s.resume_filename ?? ""}`.toLowerCase().includes(needle)) continue;
    out.push({ id: s.id, label });
    if (out.length >= 8) break;
  }
  return out;
}
