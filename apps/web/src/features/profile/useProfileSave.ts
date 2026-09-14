/**
 * @file useProfileSave
 * @description Persist profile edits: required-field gate, PUT, clear, field errors.
 *
 * Responsibilities:
 * - Block save when required fields are missing (client-side UX gate; server also validates)
 * - PUT via profileHttp with AbortSignal
 * - POST /clear after the page confirms; always replace local state with the server snapshot
 * - Surface success/error via the shared bottom-right toast (same as resume)
 * - Track which required keys failed for section highlighting
 * - Mutual exclusion: save and clear cannot run at the same time
 * - After a resolved PUT/clear, adopt the server snapshot even if aborted
 *
 * Must not own load/patch/dirty or navigation interception.
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "@/components/Toast";
import { formatApiError } from "@/lib/api/base";
import { profileHttp as api } from "@/lib/api/clients";
import type { UserProfileResponse } from "@/lib/api/contract";
// Toast texts are built inside async callbacks, not render, so resolve the
// translator at call time. Imported from "@/i18n/resolve" (not the barrel):
// the barrel re-exports LocaleProvider.tsx, which vitest cannot transform
// under the Next.js tsconfig ("jsx": "preserve"), breaking hook tests.
import { getTranslator } from "@/i18n/resolve";
import { buildProfileUpdate } from "./buildProfileUpdate";
import { isRequestAborted } from "./isRequestAborted";
import type { ProfileCompletionStats } from "./profileCompletion";
import { REQUIRED_KEYS, REQUIRED_LABELS, type RequiredKey } from "./profileRequired";

type EditorSlice = {
  profile: UserProfileResponse | null;
  adoptSaved: (snapshot: UserProfileResponse, updated: UserProfileResponse) => void;
  replaceProfile: (updated: UserProfileResponse) => void;
};

function notifySuccess(message: string) {
  toast.clear();
  toast.success(message);
}

function notifyError(message: string, durationMs?: number) {
  toast.clear();
  if (durationMs !== undefined) {
    toast.error(message, { durationMs });
    return;
  }
  toast.error(message);
}

export function useProfileSave(editor: EditorSlice, stats: ProfileCompletionStats) {
  const [saving, setSaving] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [missingRequired, setMissingRequired] = useState<RequiredKey[]>([]);
  /** Sync guard: disabled={saving|clearing} alone cannot stop same-frame double clicks. */
  const mutatingRef = useRef(false);
  const mutateAbortRef = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      mutateAbortRef.current?.abort();
    },
    [],
  );

  const abortInFlight = useCallback(() => {
    mutateAbortRef.current?.abort();
  }, []);

  const clearRequiredError = useCallback((key: keyof UserProfileResponse) => {
    if (REQUIRED_KEYS.includes(key as RequiredKey)) {
      setMissingRequired((prev) => prev.filter((k) => k !== key));
    }
  }, []);

  const handleSave = async () => {
    const { profile } = editor;
    if (!profile || mutatingRef.current) return;
    mutatingRef.current = true;
    const t = getTranslator("profile");
    const snapshot = profile;
    const missing = stats.requiredMissing;
    setMissingRequired(missing);
    if (missing.length > 0) {
      mutatingRef.current = false;
      notifyError(
        t("save.missingRequired", {
          labels: missing.map((k) => t(REQUIRED_LABELS[k])).join(t("format.listSeparator")),
        }),
        6000,
      );
      return;
    }
    setSaving(true);
    try {
      const controller = new AbortController();
      mutateAbortRef.current = controller;
      const updated = await api.updateProfile(buildProfileUpdate(snapshot), {
        signal: controller.signal,
      });
      // A resolved body means the server already committed. Adopt it even if
      // the user aborted afterwards — discard-and-leave cannot un-save.
      editor.adoptSaved(snapshot, updated);
      if (controller.signal.aborted) return;
      notifySuccess(t("save.success"));
    } catch (e) {
      if (isRequestAborted(e)) return;
      notifyError(e instanceof Error ? formatApiError(e) : t("save.failed"));
    } finally {
      mutatingRef.current = false;
      setSaving(false);
    }
  };

  const handleClear = async (): Promise<boolean> => {
    const { profile } = editor;
    if (!profile || mutatingRef.current) return false;
    mutatingRef.current = true;
    const t = getTranslator("profile");
    setClearing(true);
    try {
      const controller = new AbortController();
      mutateAbortRef.current = controller;
      const updated = await api.clearProfile({ signal: controller.signal });
      editor.replaceProfile(updated);
      setMissingRequired([]);
      if (controller.signal.aborted) return true;
      notifySuccess(t("clear.success"));
      return true;
    } catch (e) {
      if (isRequestAborted(e)) return false;
      notifyError(e instanceof Error ? formatApiError(e) : t("clear.failed"));
      return false;
    } finally {
      mutatingRef.current = false;
      setClearing(false);
    }
  };

  const requiredError = useCallback(
    (key: RequiredKey) => missingRequired.includes(key),
    [missingRequired],
  );

  return {
    saving,
    clearing,
    handleSave,
    handleClear,
    requiredError,
    clearRequiredError,
    abortInFlight,
  };
}
