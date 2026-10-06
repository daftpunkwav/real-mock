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
 */

import { useEffect, useRef } from "react";
import { getTranslator } from "@/i18n/resolve";
import { toast } from "@/components/Toast";
import { formatApiError } from "@/lib/api/base";
import type { ResumePickerItem } from "@/lib/api/contract";
import { parsePrepDeepLink } from "@/features/resume/sendToPrep";

interface UsePrepDeepLinkOptions {
  /** Gate on mount: the page sets this once the hook's collaborators exist. */
  enabled: boolean;
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

export function usePrepDeepLink({
  enabled,
  resumes,
  resumesLoaded,
  sessionsLoaded,
  setResumeId,
  startPrep,
  sendMessage,
}: UsePrepDeepLinkOptions) {
  // Hold the latest collaborators in refs so the one-shot effect below can
  // read them while it waits, without re-arming (a second run would double-send).
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

  useEffect(() => {
    if (!enabled) return;
    const link = parsePrepDeepLink(window.location.search);
    if (!link) return;
    // Consume first: a slow catalog must not leave a re-seedable URL behind.
    window.history.replaceState(null, "", window.location.pathname);
    let cancelled = false;
    void (async () => {
      const t = getTranslator("prep");
      try {
        // Wait for the resume catalog the pairing decision depends on; the
        // sessions gate only orders backend traffic (we always create here).
        const startedAt = Date.now();
        let s = stateRef.current;
        while (!s.resumesLoaded || !s.sessionsLoaded) {
          if (Date.now() - startedAt > CATALOG_WAIT_TIMEOUT_MS) break;
          await new Promise((resolve) => setTimeout(resolve, CATALOG_WAIT_MS));
          if (cancelled) return;
          s = stateRef.current;
        }
        const pairedResumeId =
          link.resumeId != null && s.resumes.some((r) => r.id === link.resumeId)
            ? link.resumeId
            : null;
        if (pairedResumeId != null) s.setResumeId(pairedResumeId);
        const sid = await s.startPrep(pairedResumeId ?? undefined);
        if (cancelled) return;
        if (sid == null) return; // create failed; its error state is already set
        // assumeViewing: startPrep resolved before the re-render committed the
        // new session to viewingRef — same bypass handleQuickPrompt uses.
        await s.sendMessage(link.question, sid, false, { assumeViewing: true });
      } catch (e) {
        if (!cancelled) {
          toast.error(e instanceof Error ? formatApiError(e) : t("chat.sendFailedFallback"));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [enabled]);
}
