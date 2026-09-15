/**
 * @file useProfileEditor
 * @description Local profile editing state: load, patch, tech-domain list, dirty baseline.
 *
 * Responsibilities:
 * - Load profile with AbortSignal (cancel stale loads on retry/unmount)
 * - Patch fields and manage tech_domains add/remove
 * - Track saved baseline for dirty detection (value equality, not object identity)
 * - Adopt server payload after a successful save without clobbering newer edits
 * - Replace local state after a confirmed clear (always take the server snapshot)
 *
 * Must not own save messaging, required-field UI errors, or navigation guards.
 *
 * `adoptSaved` still compares the in-flight snapshot by reference: that is the
 * "was this the object we sent?" check, not dirty detection.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { formatApiError, isRequestAborted } from "@/lib/api/base";
import { profileHttp as api } from "@/lib/api/clients";
import type { UserProfileResponse } from "@/lib/api/contract";
// The load-error text is built inside an async catch, not render, so resolve
// the translator at call time. Imported from "@/i18n/resolve" (not the barrel):
// the barrel re-exports LocaleProvider.tsx, which vitest cannot transform
// under the Next.js tsconfig ("jsx": "preserve"), breaking hook tests.
import { getTranslator } from "@/i18n/resolve";
import { isProfileContentEqual } from "./profileCompletion";
import { TECH_DOMAINS_MAX_COUNT } from "./profileLimits";

export function useProfileEditor() {
  const [profile, setProfile] = useState<UserProfileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  /** Persisted baseline; dirty when editable fields differ from this snapshot. */
  const savedRef = useRef<UserProfileResponse | null>(null);
  const loadAbortRef = useRef<AbortController | null>(null);

  const loadProfile = () => {
    loadAbortRef.current?.abort();
    const controller = new AbortController();
    loadAbortRef.current = controller;
    setLoading(true);
    setLoadError("");
    api
      .getProfile({ signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        savedRef.current = data;
        setProfile(data);
      })
      .catch((e) => {
        if (controller.signal.aborted || isRequestAborted(e)) return;
        setLoadError(e instanceof Error ? formatApiError(e) : getTranslator("profile")("load.failed"));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  };

  useEffect(() => {
    loadProfile();
    return () => loadAbortRef.current?.abort();
  }, []);

  const dirty =
    profile !== null &&
    savedRef.current !== null &&
    !isProfileContentEqual(profile, savedRef.current);

  const patch = <K extends keyof UserProfileResponse>(key: K, value: UserProfileResponse[K]) => {
    if (!profile) return;
    setProfile({ ...profile, [key]: value });
  };

  const addDomain = () => {
    if (!profile || profile.tech_domains.length >= TECH_DOMAINS_MAX_COUNT) return;
    setProfile({ ...profile, tech_domains: [...profile.tech_domains, ""] });
  };

  const removeDomain = (i: number) => {
    if (!profile) return;
    const domains = profile.tech_domains.filter((_, idx) => idx !== i);
    setProfile({ ...profile, tech_domains: domains.length ? domains : [""] });
  };

  const adoptSaved = (snapshot: UserProfileResponse, updated: UserProfileResponse) => {
    savedRef.current = updated;
    setProfile((current) => (current === snapshot ? updated : current));
  };

  const replaceProfile = (updated: UserProfileResponse) => {
    savedRef.current = updated;
    setProfile(updated);
  };

  return {
    profile,
    loading,
    loadError,
    dirty,
    loadProfile,
    patch,
    addDomain,
    removeDomain,
    adoptSaved,
    replaceProfile,
  };
}
