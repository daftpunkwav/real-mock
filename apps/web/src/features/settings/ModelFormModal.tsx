"use client";

/** Centered modal wrapping the model form for the add and edit flows. Escape
 * closes unless a save is in flight; title follows the flow via ``titleKey``. */

import { useEffect } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import type { Dispatch, SetStateAction } from "react";
import type { ChannelModelCatalog } from "@/types";
import { useDialogScrollLock } from "@/components/useDialogScrollLock";
import { useT } from "@/i18n";
import { type ModelDraft } from "./constants";
import { ModelForm } from "./ModelForm";

export function ModelFormModal({
  draft,
  setDraft,
  catalog,
  catalogLoading,
  onFetchCatalog,
  onSave,
  onCancel,
  saving,
  titleKey = "modelList.add",
}: {
  draft: ModelDraft;
  setDraft: Dispatch<SetStateAction<ModelDraft>>;
  catalog: ChannelModelCatalog | null;
  catalogLoading: boolean;
  onFetchCatalog: () => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
  titleKey?: "modelList.add" | "modelList.edit";
}) {
  const t = useT("settings");
  useDialogScrollLock(true);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !saving) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [saving, onCancel]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 anim-fade-in"
      role="dialog"
      aria-modal="true"
      aria-label={t(titleKey)}
    >
      <div className="surface-card w-full max-w-lg !p-5 anim-rise">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-[13px] font-semibold text-ink">{t(titleKey)}</h2>
          <button
            type="button"
            className="rounded p-0.5 text-ink-subtle hover:text-ink"
            aria-label={t("modelForm.cancel")}
            onClick={onCancel}
          >
            <X size={14} />
          </button>
        </div>
        <ModelForm
          draft={draft}
          setDraft={setDraft}
          catalog={catalog}
          catalogLoading={catalogLoading}
          onFetchCatalog={onFetchCatalog}
          onCancel={onCancel}
          onSave={onSave}
          saving={saving}
        />
      </div>
    </div>,
    document.body,
  );
}
