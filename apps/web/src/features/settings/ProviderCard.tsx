"use client";

/** Provider header card: identity only (name / enable state / website / notes / delete).
 * Connection settings live on the per-kind channel cards below. */

import { useEffect, useState } from "react";
import { Save, Trash2 } from "lucide-react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { settingsHttp } from "@/lib/api/clients";
import { toast } from "@/components/Toast";
import { useT } from "@/i18n";
import type { ProviderWithModels } from "@/types";

export function ProviderCard({
  provider,
  onChanged,
}: {
  provider: ProviderWithModels;
  onChanged: () => Promise<void>;
}) {
  const [name, setName] = useState(provider.name);
  const [enabled, setEnabled] = useState(provider.enabled);
  const [websiteUrl, setWebsiteUrl] = useState(provider.website_url);
  const [notes, setNotes] = useState(provider.notes);
  const [saving, setSaving] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const t = useT("settings");
  const tc = useT("common");

  useEffect(() => {
    setName(provider.name);
    setEnabled(provider.enabled);
    setWebsiteUrl(provider.website_url);
    setNotes(provider.notes);
  }, [provider.id, provider.name, provider.enabled, provider.website_url, provider.notes]);

  const save = async () => {
    setSaving(true);
    try {
      await settingsHttp.updateProvider(provider.id, {
        name,
        enabled,
        website_url: websiteUrl,
        notes,
      });
      toast.success(t("providerCard.saved"));
      await onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("providerCard.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    setDeleting(true);
    try {
      await settingsHttp.deleteProvider(provider.id);
      toast.success(t("providerCard.deleted"));
      setConfirmingDelete(false);
      await onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("providerCard.deleteFailed"));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="surface-card !p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="min-w-0 flex-1 sm:max-w-sm">
          <label className="mb-1 block text-[11px] text-ink-muted">{t("providerCard.name.label")}</label>
          <input className="field-input !h-9 w-full" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <label className="flex items-center gap-1.5 text-[12px] text-ink-muted sm:pb-2.5">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          {t("providerCard.enabled")}
        </label>
      </div>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">{t("providerCard.website.label")}</label>
          <input
            className="field-input !h-9"
            placeholder={t("providerCard.website.placeholder")}
            value={websiteUrl}
            onChange={(e) => setWebsiteUrl(e.target.value)}
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">{t("providerCard.notes.label")}</label>
          <input className="field-input !h-9" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
      </div>
      <div className="mt-3 flex items-center justify-end gap-2">
        <button
          type="button"
          className="flex items-center gap-1 rounded-md border border-surface-border px-2.5 py-1.5 text-[12px] text-ink-muted transition-colors hover:border-[var(--danger)] hover:text-[var(--danger)]"
          onClick={() => setConfirmingDelete(true)}
        >
          <Trash2 size={13} /> {t("providerCard.delete")}
        </button>
        <button type="button" className="btn-primary !h-8" onClick={save} disabled={saving}>
          <Save size={13} /> {saving ? t("providerCard.saving") : t("providerCard.save")}
        </button>
      </div>

      <ConfirmDialog
        open={confirmingDelete}
        title={t("providerCard.deleteConfirmTitle")}
        message={t("providerCard.deleteConfirmMessage", { name: provider.name })}
        confirmLabel={t("providerCard.delete")}
        cancelLabel={tc("confirm.cancel")}
        busy={deleting}
        onConfirm={remove}
        onCancel={() => setConfirmingDelete(false)}
      />
    </div>
  );
}
