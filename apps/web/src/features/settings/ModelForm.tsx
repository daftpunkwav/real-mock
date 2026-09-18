"use client";

/** Model create and edit form, hosted by ModelFormModal (which owns the dialog
 * frame). The model-name field is a lightweight combobox: "fetch model list" pulls
 * candidate ids from the vendor descriptor or the provider's /models endpoint and
 * offers them in a popover under the input (filtered by the typed text); manual
 * entry stays available at all times.
 *
 * The capability-config panel is a zcode-style JSON projection of the form plus the
 * capability convention keys in extras; "Apply" writes an edited snippet back into
 * the form fields (which stay canonical). Unapplied edits are lost when any form
 * field changes — the panel re-derives from the draft on every draft update. */

import { useEffect, useState } from "react";
import { Download, Save, X } from "lucide-react";
import { toast } from "@/components/Toast";
import { useT } from "@/i18n";
import type { ChannelModelCatalog } from "@/types";
import { applyCapabilityConfig, capsConfigFromDraft } from "./capabilityConfig";
import { CAP_OPTIONS, type ModelDraft } from "./constants";

export function ModelForm({
  draft,
  setDraft,
  catalog,
  catalogLoading,
  onFetchCatalog,
  onSave,
  onCancel,
  saving,
}: {
  draft: ModelDraft;
  setDraft: (d: ModelDraft) => void;
  catalog: ChannelModelCatalog | null;
  catalogLoading: boolean;
  onFetchCatalog: () => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const t = useT("settings");
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [capsText, setCapsText] = useState("");
  const query = draft.model.trim().toLowerCase();
  const candidates =
    catalog?.models.filter((m) => !query || m.toLowerCase().includes(query)) ?? [];

  // The JSON panel re-derives from the form (canonical) on every draft change;
  // unapplied manual edits in the textarea are intentionally discarded.
  useEffect(() => {
    setCapsText(JSON.stringify(capsConfigFromDraft(draft), null, 2));
  }, [draft]);

  const applyCaps = () => {
    const result = applyCapabilityConfig(capsText, draft);
    if (!result.ok) {
      toast.error(t("toast.capsInvalidJson"));
      return;
    }
    setDraft(result.draft);
  };

  // A freshly fetched catalog opens the candidate popover automatically.
  useEffect(() => {
    if (catalog && catalog.models.length > 0) setCatalogOpen(true);
  }, [catalog]);

  return (
    <div>
      <div className="grid grid-cols-1 gap-2.5">
        <div>
          <div className="mb-1 flex items-center justify-between">
            <label className="text-[11px] text-ink-muted">{t("modelForm.model.label")}</label>
            <button
              type="button"
              className="flex items-center gap-1 text-[11px] text-[var(--primary)] hover:underline disabled:opacity-50"
              disabled={catalogLoading}
              onClick={onFetchCatalog}
            >
              <Download size={11} />
              {catalogLoading ? t("catalog.loading") : t("catalog.fetch")}
            </button>
          </div>
          <div className="relative">
            <input
              className="field-input !h-9"
              value={draft.model}
              placeholder={t("modelForm.model.placeholder")}
              onChange={(e) => {
                setDraft({ ...draft, model: e.target.value });
                setCatalogOpen(true);
              }}
              onFocus={() => {
                if (candidates.length > 0) setCatalogOpen(true);
              }}
              onClick={() => {
                // Focus alone does not re-fire when the field is already focused.
                if (candidates.length > 0) setCatalogOpen(true);
              }}
              onBlur={() => setCatalogOpen(false)}
              onKeyDown={(e) => {
                if (e.key === "Escape" && catalogOpen) {
                  // Swallow so a host dialog does not also close.
                  e.stopPropagation();
                  setCatalogOpen(false);
                }
              }}
            />
            {catalogOpen && candidates.length > 0 && (
              <div
                role="listbox"
                aria-label={t("catalog.pickAria")}
                // Keep focus on the input so onBlur does not close before click.
                onMouseDown={(e) => e.preventDefault()}
                className="surface-card absolute top-full z-20 mt-1 max-h-56 w-full overflow-y-auto !p-1"
              >
                {candidates.map((m) => (
                  <button
                    key={m}
                    type="button"
                    role="option"
                    aria-selected={m === draft.model}
                    className="flex h-8 w-full items-center rounded-md px-2.5 text-left text-[12px] text-ink transition-colors hover:bg-surface-muted"
                    onClick={() => {
                      setDraft({ ...draft, model: m });
                      setCatalogOpen(false);
                    }}
                  >
                    <span className="min-w-0 truncate">{m}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
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
          {t("modelForm.capsConfig.summary")}
        </summary>
        <textarea
          className="field-input mt-1.5 min-h-40 w-full font-mono text-[11px]"
          value={capsText}
          onChange={(e) => setCapsText(e.target.value)}
          spellCheck={false}
        />
        <div className="mt-1.5 flex justify-end">
          <button
            type="button"
            className="flex items-center gap-1 rounded-md border border-surface-border px-2.5 py-1 text-[11px] text-ink-muted hover:text-ink"
            onClick={applyCaps}
          >
            {t("modelForm.capsConfig.apply")}
          </button>
        </div>
      </details>

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
