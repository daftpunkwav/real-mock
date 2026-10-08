"use client";

/**
 * @file usePrepDeepLink
 * @description Consumes the resume-review → prep deep link (`/prep?resume=&q=`).
 *
 * Runs once per page load after the resumes and sessions catalogs settle:
 * opens a fresh prep session bound to the linked resume (the drill gets its
 * own focused thread; the sessions panel groups by resume) and sends the
 * seeded question. The URL params are stripped immediately so a refresh
 * cannot re-send.
 *
 * One-shot semantics survive StrictMode's effect → cleanup → effect cycle:
 * the consumed flag is a ref (not the URL), the async work is disowned
 * rather than cancelled by cleanup (cancelling there would kill the only
 * run), and a StrictMode remount re-owns the in-flight work by flipping the
 * alive flag back on. A real unmount flips it off for good, and every await
 * checks it before touching state.
 */

import { useEffect, useRef } from "react";
import { getTranslator } from "@/i18n/resolve";
import { toast } from "@/components/Toast";
import { formatApiError } from "@/lib/api/base";
import type { ResumePickerItem } from "@/lib/api/contract";
import { parsePrepDeepLink } from "@/features/resume/sendToPrep";

interface UsePrepDeepLinkOptions {
  resumes: ResumePickerItem[];
  resumesLoaded: boolean;
  sessionsLoaded: boolean;
  setResumeId: (id: number | null) => void;
  /** Create a session; the argument binds the resume before state commits. */
  startPrep: (resumeOverride?: number) => Promise<number | null>;
  /** Same pipeline as the composer send (session-scoped, view-aware). */
  sendMessage: (
    text: string,
    sessionId?: number,
    skipUserMessage?: boolean,
    opts?: { assumeViewing?: boolean },
  ) => Promise<boolean>;
}

/** Poll interval while waiting for the resumes/sessions catalogs to settle. */
const CATALOG_WAIT_MS = 120;
/** Upper bound on the catalog wait: a hung backend must not spin forever. */
const CATALOG_WAIT_TIMEOUT_MS = 10_000;

/** Snapshot of the hook collaborators the deep-link runner reads while waiting. */
interface CatalogState {
  resumes: ResumePickerItem[];
  resumesLoaded: boolean;
  sessionsLoaded: boolean;
  setResumeId: (id: number | null) => void;
  startPrep: (resumeOverride?: number) => Promise<number | null>;
  sendMessage: (
    text: string,
    sessionId?: number,
    skipUserMessage?: boolean,
    opts?: { assumeViewing?: boolean },
  ) => Promise<boolean>;
}

/**
 * Poll until the resumes/sessions catalogs settle (bounded by the timeout and
 * cut short by unmount); returns the latest snapshot to run against.
 */
const waitForCatalogs = async (
  stateRef: React.MutableRefObject<CatalogState>,
  aliveRef: React.MutableRefObject<boolean>,
): Promise<CatalogState> => {
  const startedAt = Date.now();
  let catalogs = stateRef.current;
  while (
    aliveRef.current &&
    (!catalogs.resumesLoaded || !catalogs.sessionsLoaded) &&
    Date.now() - startedAt <= CATALOG_WAIT_TIMEOUT_MS
  ) {
    await new Promise((resolve) => setTimeout(resolve, CATALOG_WAIT_MS));
    catalogs = stateRef.current;
  }
  return catalogs;
};

/** Linked resume id when it exists in the loaded catalog; null otherwise. */
const resolvePairedResumeId = (
  link: { resumeId: number | null },
  resumes: ResumePickerItem[],
): number | null =>
  link.resumeId != null && resumes.some((r) => r.id === link.resumeId) ? link.resumeId : null;

export const usePrepDeepLink = ({
  resumes,
  resumesLoaded,
  sessionsLoaded,
  setResumeId,
  startPrep,
  sendMessage,
}: UsePrepDeepLinkOptions) => {
  // Hold the latest collaborators in refs so the disowned async below reads
  // fresh values while it waits, without re-arming the one-shot effect.
  const stateRef = useRef({
    resumes,
    resumesLoaded,
    sessionsLoaded,
    setResumeId,
    startPrep,
    sendMessage,
  });
  useEffect(() => {
    stateRef.current = {
      resumes,
      resumesLoaded,
      sessionsLoaded,
      setResumeId,
      startPrep,
      sendMessage,
    };
  });
  /** Guard against a second consumption (StrictMode remount included). */
  const consumedRef = useRef(false);
  /** False once the host unmounts for real; every await re-checks it. */
  const aliveRef = useRef(true);

  useEffect(() => {
    // StrictMode remount: the first run's async was disowned by our cleanup;
    // re-own it so it keeps going. (The URL is already stripped, so the
    // consumed check must come before the param parse.)
    if (consumedRef.current) {
      aliveRef.current = true;
    } else {
      const link = parsePrepDeepLink(window.location.search);
      if (link) {
        consumedRef.current = true;
        // Consume first: a slow catalog must not leave a re-seedable URL.
        window.history.replaceState(null, "", window.location.pathname);
        const run = async () => {
          const translator = getTranslator("prep");
          try {
            // Wait for the resume catalog the pairing decision depends on; the
            // sessions gate only orders backend traffic (we always create here).
            const catalogs = await waitForCatalogs(stateRef, aliveRef);
            const pairedResumeId = resolvePairedResumeId(link, catalogs.resumes);
            if (pairedResumeId != null) catalogs.setResumeId(pairedResumeId);
            const sid = await catalogs.startPrep(pairedResumeId ?? undefined);
            if (!aliveRef.current) return;
            if (sid == null) return; // create failed; its error state is already set
            // assumeViewing: startPrep resolved before the re-render committed
            // the new session to viewingRef — same bypass handleQuickPrompt uses.
            await catalogs.sendMessage(link.question, sid, false, { assumeViewing: true });
          } catch (e) {
            if (aliveRef.current) {
              toast.error(
                e instanceof Error ? formatApiError(e) : translator("chat.sendFailedFallback"),
              );
            }
          }
        };
        // Fire-and-forget: errors are handled inside; keep the effect sync.
        void run();
      }
    }
    // The cleanup only disowns a run that actually started; for a no-link or
    // re-own pass the flag flip is harmless.
    return () => {
      aliveRef.current = false;
    };
  }, []);
};
