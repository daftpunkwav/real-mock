/**
 * @file compactionArchive.ts
 * @description Display-only archive of folded turns: after a compaction the
 * backend rewrites history (old turns live on only in the summary), but the
 * UI keeps every message visible by archiving the folded view-models locally.
 * Groups persist per session in localStorage (bounded, best-effort) so a
 * refresh restores them; each group links the backup session that holds the
 * verbatim originals for fork-from-point restores.
 *
 * Privacy note: folded turns are user conversation text in plaintext. Entries
 * are removed on session delete/clear via clearArchive; no cross-device sync
 * is performed. A future logout flow should sweep ARCHIVE_KEY_PREFIX keys.
 */

import type { PrepChatMessage } from "./types";

/** One folded batch: the visible turns a single compaction replaced. */
export interface ArchivedGroup {
  /** Compaction summary version that replaced this batch. */
  version: number;
  /** Backend length before the compaction (fork anchor). */
  forkPoint: number;
  /** Backup session holding the verbatim originals (null when none). */
  backupSessionId: number | null;
  /** True once a later rolling compaction deleted this backup (view-only). */
  staleBackup: boolean;
  /** Folded view-models in original order (archived copies). */
  messages: PrepChatMessage[];
}

/** All archived batches of one session, oldest first. */
export interface CompactionArchive {
  groups: ArchivedGroup[];
}

const ARCHIVE_KEY_PREFIX = "realmock_prep_archive_";
/** Max archived messages per session (summaries chain preserves the content). */
const ARCHIVE_MAX_MESSAGES = 300;

function keyFor(sessionId: number): string {
  return `${ARCHIVE_KEY_PREFIX}${sessionId}`;
}

function isMessage(value: unknown): value is PrepChatMessage {
  const m = value as PrepChatMessage;
  return !!m && typeof m === "object" && typeof m.id === "string" && typeof m.content === "string";
}

/** Strip live-only fields so stored groups never resurrect streaming state. */
export function toArchivedCopy(m: PrepChatMessage): PrepChatMessage {
  const id = m.id.startsWith("archived-") ? m.id : `archived-${m.id}`;
  return {
    // Prefixed ids: fresh reloads remap the same turns with new ids, and
    // React keys plus message lookups must never collide across the boundary.
    id,
    role: m.role,
    content: m.content,
    ...(m.steps ? { steps: m.steps } : {}),
    ...(m.searchGroups ? { searchGroups: m.searchGroups } : {}),
    ...(m.thinking ? { thinking: m.thinking } : {}),
    ...(m.trace ? { trace: m.trace } : {}),
    ...(m.stopped ? { stopped: true } : {}),
    ...(m.backendIndex !== undefined ? { backendIndex: m.backendIndex } : {}),
    ...(m.compaction ? { compaction: m.compaction } : {}),
  };
}

/** Load the stored archive; null on any anomaly (never throws). */
export function loadArchive(sessionId: number): CompactionArchive | null {
  try {
    if (typeof window === "undefined" || !window.localStorage) return null;
    const raw = window.localStorage.getItem(keyFor(sessionId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CompactionArchive;
    if (!parsed || !Array.isArray(parsed.groups)) return null;
    const groups: ArchivedGroup[] = [];
    for (const g of parsed.groups) {
      if (!g || !Array.isArray(g.messages)) continue;
      // Already normalized on push; validate shape only (no re-copy, so ids
      // never gain a second prefix across save/load cycles).
      const messages = g.messages.filter(isMessage);
      if (messages.length === 0) continue;
      groups.push({
        version: Number(g.version) || 0,
        forkPoint: Number(g.forkPoint) || 0,
        backupSessionId: typeof g.backupSessionId === "number" ? g.backupSessionId : null,
        staleBackup: g.staleBackup === true,
        messages,
      });
    }
    return groups.length > 0 ? { groups } : null;
  } catch {
    return null;
  }
}

function persist(sessionId: number, archive: CompactionArchive): void {
  try {
    window.localStorage.setItem(keyFor(sessionId), JSON.stringify(archive));
  } catch {
    // Quota or privacy mode: in-memory display still works this session.
  }
}

/**
 * Push a newly folded batch: older groups' backups were retired by the
 * rolling backend backup, so they become view-only; the total stays bounded
 * by dropping the oldest batches first.
 */
export function pushArchivedGroup(sessionId: number, group: ArchivedGroup): CompactionArchive {
  const current = loadArchive(sessionId) ?? { groups: [] };
  const groups = current.groups.map((g) => ({ ...g, staleBackup: true }));
  groups.push({ ...group, staleBackup: false, messages: group.messages.map(toArchivedCopy) });
  let total = groups.reduce((n, g) => n + g.messages.length, 0);
  while (groups.length > 1 && total > ARCHIVE_MAX_MESSAGES) {
    const dropped = groups.shift();
    total -= dropped?.messages.length ?? 0;
  }
  const next = { groups };
  persist(sessionId, next);
  return next;
}

/** Drop the stored archive (session deleted or user-cleared). */
export function clearArchive(sessionId: number): void {
  try {
    window.localStorage.removeItem(keyFor(sessionId));
  } catch {
    // Non-fatal.
  }
}
