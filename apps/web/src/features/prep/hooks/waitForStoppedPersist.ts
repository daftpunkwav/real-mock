/**
 * @file waitForStoppedPersist.ts
 * @description Shared poll-until-stable confirmation that a stopped stream's
 * server-side persist has landed, before trusting that session's history
 * length (compact/retract guards). Replaces fixed grace delays that either
 * waste time or lose to a slow persist.
 */

import { prepCoachHttp as api } from "@/lib/api/clients";

/** Poll budget and interval for the stopped-persist confirmation. */
const PERSIST_WAIT_BUDGET_MS = 2500;
const PERSIST_WAIT_INTERVAL_MS = 250;

/**
 * Poll history until two consecutive reads agree (or the budget runs out),
 * then hand the settled length to `applyCount`. Transport errors exit fast
 * without applying (callers keep their fallback resync paths). Never rejects;
 * `shouldContinue` lets callers stop early (e.g. after unmount).
 */
export async function waitForStoppedPersist(
  sid: number,
  applyCount: (sid: number, n: number) => void,
  shouldContinue?: () => boolean,
): Promise<void> {
  const deadline = Date.now() + PERSIST_WAIT_BUDGET_MS;
  let prev = -1;
  while (Date.now() < deadline) {
    if (shouldContinue && !shouldContinue()) return;
    try {
      const list = await api.prepMessages(sid);
      if (shouldContinue && !shouldContinue()) return;
      const n = Array.isArray(list) ? list.length : 0;
      if (n === prev) {
        applyCount(sid, n);
        return;
      }
      prev = n;
    } catch {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, PERSIST_WAIT_INTERVAL_MS));
  }
}
