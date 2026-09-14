/**
 * @file askTimeout.ts
 * @description Ask-dialog auto-resolve timeout (seconds, localStorage-backed).
 * When the coach opens a question dialog with a recommended choice and the
 * user does not answer in time, the UI auto-submits the recommendation.
 * 0 disables the timeout.
 */

/** localStorage key for the timeout setting. */
export const ASK_TIMEOUT_KEY = "realmock_prep_ask_timeout_sec";

/** Default wait before auto-selecting the recommended choice (3 minutes). */
export const ASK_TIMEOUT_DEFAULT_SEC = 180;

/** Selectable timeout values in seconds (0 = never auto-select). */
export const ASK_TIMEOUT_OPTIONS = [0, 60, 180, 300, 600];

/** Read the configured timeout; falls back to the default on any anomaly. */
export function readAskTimeoutSec(): number {
  try {
    if (typeof window === "undefined" || !window.localStorage) return ASK_TIMEOUT_DEFAULT_SEC;
    const raw = window.localStorage.getItem(ASK_TIMEOUT_KEY);
    if (raw === null) return ASK_TIMEOUT_DEFAULT_SEC;
    const seconds = Number(raw);
    return ASK_TIMEOUT_OPTIONS.includes(seconds) ? seconds : ASK_TIMEOUT_DEFAULT_SEC;
  } catch {
    return ASK_TIMEOUT_DEFAULT_SEC;
  }
}

/** Persist the timeout; ignores storage failures (private-mode browsers). */
export function writeAskTimeoutSec(seconds: number): void {
  try {
    window.localStorage.setItem(ASK_TIMEOUT_KEY, String(seconds));
  } catch {
    // Non-fatal: the default applies next load.
  }
}
