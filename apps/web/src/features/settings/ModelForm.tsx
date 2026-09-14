"use client";

/** Model create and edit form. */

import { Save, X } from "lucide-react";
import { useT } from "@/i18n";
import { CAP_OPTIONS, type ModelDraft } from "./constants";

export function ModelForm({
  draft,
  setDraft,
  onSave,
  onCancel,
  saving,
}: {
  draft: ModelDraft;
  setDraft: (d: ModelDraft) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const t = useT("settings");

  return (
    <div className="rounded-md border border-[var(--primary)]/40 bg-[var(--info-soft)]/40 p-3">
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">{t("modelForm.model.label")}</label>
          <input
            className="field-input !h-9"
            value={draft.model}
            placeholder={t("modelForm.model.placeholder")}
            onChange={(e) => setDraft({ ...draft, model: e.target.value })}
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">{t("modelForm.displayName.label")}</label>
          <input
            className="field-input !h-9"
            value={draft.display_name}
            onChange={(e) => setDraft({ ...draft, display_name: e.target.value })}
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">{t("modelForm.contextWindow.label")}</label>
          <input
            className="field-input !h-9"
            type="number"
            min={0}
            value={draft.context_window}
            onChange={(e) => setDraft({ ...draft, context_window: e.target.value })}
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">{t("modelForm.maxOutput.label")}</label>
          <input
            className="field-input !h-9"
            type="number"
            min={1}
            value={draft.max_output}
            onChange={(e) => setDraft({ ...draft, max_output: e.target.value })}
          />
        </div>
      </div>

      <div className="mt-2.5">
        <p className="mb-1 text-[11px] text-ink-muted">{t("modelForm.capabilities.label")}</p>
        <div className="flex flex-wrap gap-x-4 gap-y-1.5">
          {CAP_OPTIONS.map(({ key, labelKey }) => (
            <label key={key} className="flex items-center gap-1.5 text-[12px] text-ink-muted">
              <input
                type="checkbox"
                checked={draft.capabilities[key]}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    capabilities: { ...draft.capabilities, [key]: e.target.checked },
                  })
                }
              />
              {t(labelKey)}
            </label>
          ))}
        </div>
      </div>

      <details className="mt-2.5">
        <summary className="cursor-pointer text-[11px] text-ink-subtle hover:text-ink-muted">
          {t("modelForm.extras.summary")}
        </summary>
        <textarea
          className="field-input mt-1.5 min-h-16 w-full font-mono text-[11px]"
          value={draft.extras_text}
          onChange={(e) => setDraft({ ...draft, extras_text: e.target.value })}
          spellCheck={false}
        />
      </details>

      <div className="mt-3 flex justify-end gap-2">
        <button
          type="button"
          className="flex items-center gap-1 rounded-md border border-surface-border px-2.5 py-1.5 text-[12px] text-ink-muted hover:text-ink"
          onClick={onCancel}
        >
          <X size={13} /> {t("modelForm.cancel")}
        </button>
        <button type="button" className="btn-primary !h-8" onClick={onSave} disabled={saving}>
          <Save size={13} /> {saving ? t("modelForm.saving") : t("modelForm.save")}
        </button>
      </div>
    </div>
  );
}
