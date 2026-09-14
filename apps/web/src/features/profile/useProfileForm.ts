/**
 * @file useProfileForm
 * @description Profile page facade: compose editor, save, completion stats, and nav guard.
 *
 * Responsibilities:
 * - Wire useProfileEditor + useProfileSave + useUnsavedNavigation
 * - Expose a stable API for the profile page
 * - Abort in-flight save/clear when the user confirms discard-and-leave
 * - Clear required-field errors from the page-level patch wrapper
 *
 * Must not render UI; page components consume the returned API.
 * Dialogs are owned by the page (shared ConfirmDialog), not this hook.
 */

"use client";

import { useCallback, useMemo } from "react";
import type { UserProfileResponse } from "@/lib/api/contract";
import { completionStatsOf, isProfileBlank } from "./profileCompletion";
import { useProfileEditor } from "./useProfileEditor";
import { useProfileSave } from "./useProfileSave";
import { useUnsavedNavigation } from "./useUnsavedNavigation";

export function useProfileForm() {
  const editor = useProfileEditor();
  const stats = useMemo(() => completionStatsOf(editor.profile), [editor.profile]);
  const save = useProfileSave(editor, stats);
  const nav = useUnsavedNavigation(editor.dirty);
  const canClear =
    editor.profile !== null && (editor.dirty || !isProfileBlank(editor.profile));

  const patch = <K extends keyof UserProfileResponse>(key: K, value: UserProfileResponse[K]) => {
    editor.patch(key, value);
    save.clearRequiredError(key);
  };

  const leavePage = useCallback(() => {
    save.abortInFlight();
    nav.leavePage();
  }, [save.abortInFlight, nav.leavePage]);

  return {
    profile: editor.profile,
    loading: editor.loading,
    loadError: editor.loadError,
    saving: save.saving,
    clearing: save.clearing,
    dirty: editor.dirty,
    canClear,
    pendingNav: nav.pendingNav,
    stayOnPage: nav.stayOnPage,
    leavePage,
    stats,
    loadProfile: editor.loadProfile,
    patch,
    handleSave: save.handleSave,
    handleClear: save.handleClear,
    addDomain: editor.addDomain,
    removeDomain: editor.removeDomain,
    requiredError: save.requiredError,
  };
}
