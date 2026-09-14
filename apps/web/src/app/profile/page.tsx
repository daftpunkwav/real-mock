"use client";

/**
 * @file page.tsx
 * @description Profile page composing form sections, preview/completion sidebars, and unsaved-change guard.
 *
 * Responsibilities:
 * - Wire useProfileForm into loading / error / ready UI states
 * - Render editable profile sections plus sticky preview and completion cards
 * - Show save/clear feedback via the shared bottom-right toast
 * - Guard unsaved navigation and confirm before persisting an empty profile
 *
 * Dialogs use the shared ConfirmDialog (same as resume). Spinners use the
 * shared Spinner. Do not reintroduce feature-local copies.
 */

import { useState } from "react";
import { Eraser, Save } from "lucide-react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { LoadError } from "@/components/LoadError";
import { Spinner } from "@/components/Spinner";
import { useT } from "@/i18n";
import {
  BasicInfoSection,
  CompletionCard,
  EducationSection,
  JobIntentSection,
  OnlineIdentitySection,
  PageHead,
  PreviewCard,
  SkillsSection,
  useProfileForm,
} from "@/features/profile";

const PAGE_SHELL = "page-shell";

export default function ProfilePage() {
  const t = useT("profile");
  const [clearOpen, setClearOpen] = useState(false);
  const {
    profile,
    loading,
    loadError,
    saving,
    clearing,
    dirty,
    canClear,
    pendingNav,
    stayOnPage,
    leavePage,
    stats,
    loadProfile,
    patch,
    handleSave,
    handleClear,
    addDomain,
    removeDomain,
    requiredError,
  } = useProfileForm();
  const busy = saving || clearing;

  if (loading) {
    return (
      <div className={PAGE_SHELL}>
        <PageHead />
        <div className="flex items-center justify-center gap-2 py-16 text-[13px] text-ink-muted">
          <Spinner className="h-4 w-4" />
          {t("page.loading")}
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className={PAGE_SHELL}>
        <PageHead />
        <LoadError message={loadError} onRetry={loadProfile} />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className={PAGE_SHELL}>
        <PageHead />
        <LoadError message={t("load.failed")} onRetry={loadProfile} />
      </div>
    );
  }

  return (
    <div className={`${PAGE_SHELL} anim-rise`}>
      <div className="page-header">
        <PageHead />
        <div className="flex shrink-0 items-center gap-3">
          <button
            type="button"
            onClick={() => setClearOpen(true)}
            disabled={busy || !canClear}
            className="btn-secondary !text-[var(--danger-ink)] hover:!border-[var(--danger)]/40 hover:!bg-[var(--danger-soft)]"
          >
            {clearing ? <Spinner className="h-3.5 w-3.5" /> : <Eraser size={13} />}
            {t("page.clear")}
          </button>
          <button type="button" onClick={handleSave} disabled={busy} className="btn-primary">
            {saving ? <Spinner className="h-3.5 w-3.5" /> : <Save size={13} />}
            {t("page.save")}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-4">
          <BasicInfoSection profile={profile} patch={patch} requiredError={requiredError} />
          <EducationSection profile={profile} patch={patch} requiredError={requiredError} />
          <JobIntentSection profile={profile} patch={patch} requiredError={requiredError} />
          <OnlineIdentitySection profile={profile} patch={patch} requiredError={requiredError} />
          <SkillsSection
            profile={profile}
            patch={patch}
            requiredError={requiredError}
            onAddDomain={addDomain}
            onRemoveDomain={removeDomain}
          />
        </div>

        <aside className="space-y-4 xl:sticky xl:top-6">
          <PreviewCard profile={profile} filledDomains={stats.filledDomains} />
          <CompletionCard stats={stats} />
        </aside>
      </div>

      {/* Closes when a completed save clears dirty while the dialog is open. */}
      <ConfirmDialog
        open={pendingNav !== null && dirty}
        title={t("unsaved.title")}
        message={t("unsaved.body")}
        cancelLabel={t("unsaved.stay")}
        confirmLabel={t("unsaved.leave")}
        onCancel={stayOnPage}
        onConfirm={leavePage}
      />
      <ConfirmDialog
        open={clearOpen}
        busy={clearing}
        title={t("clear.title")}
        message={t("clear.body")}
        cancelLabel={t("clear.cancel")}
        confirmLabel={t("clear.confirm")}
        onCancel={() => {
          if (!clearing) setClearOpen(false);
        }}
        onConfirm={() => {
          // Close only on success; the page leaves busy on either outcome.
          void handleClear().then((ok) => {
            if (ok) setClearOpen(false);
          });
        }}
      />
    </div>
  );
}
