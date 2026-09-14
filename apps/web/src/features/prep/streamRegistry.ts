/**
 * @file streamRegistry.ts
 * @description Module-level registry of in-flight prep streams, keyed by session id.
 * Module scope (not React state) keeps generations alive across session switches
 * and in-app navigation: only closing or refreshing the site drops them.
 * At most one stream per session; starting another queues behind it.
 * Subscribe for UI badges: listeners fire with the active id list on every change.
 */

/**
 * Grace period for the server to persist a stopped turn before the client
 * mutates that session's history (delete/clear/retract/regenerate).
 */
export const STREAM_STOP_GRACE_MS = 400;

type StreamListener = (activeIds: number[]) => void;

/** Session ids with a live generation stream. */
const activeControllers = new Map<number, AbortController>();

const listeners = new Set<StreamListener>();

function notify(): void {
  if (listeners.size === 0) return;
  const ids = [...activeControllers.keys()];
  for (const listener of listeners) listener(ids);
}

/** Subscribe to active-stream changes; returns an unsubscribe function. */
export function subscribeStreams(listener: StreamListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Snapshot of sessions with a live generation stream. */
export function activeStreamIds(): number[] {
  return [...activeControllers.keys()];
}

/** Register a stream controller for a session (replaces any stale entry). */
export function registerStream(sessionId: number, controller: AbortController): void {
  activeControllers.set(sessionId, controller);
  notify();
}

/** Forget a finished stream; returns true when an entry was removed. */
export function completeStream(sessionId: number): boolean {
  const removed = activeControllers.delete(sessionId);
  if (removed) notify();
  return removed;
}

/** Abort the live stream of a session; returns false when none was running. */
export function abortStream(sessionId: number): boolean {
  const controller = activeControllers.get(sessionId);
  if (!controller) return false;
  activeControllers.delete(sessionId);
  notify();
  controller.abort();
  return true;
}

/** Whether a session currently has a live generation stream. */
export function hasActiveStream(sessionId: number): boolean {
  return activeControllers.has(sessionId);
}

/** Test-only reset. */
export function clearStreamsForTests(): void {
  activeControllers.clear();
  listeners.clear();
}
