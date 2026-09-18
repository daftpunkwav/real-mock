"use client";

import { Cpu, Plus } from "lucide-react";
import type { Dispatch, SetStateAction } from "react";
import type { ModelKind, ModelProfile, ProviderWithModels } from "@/types";
import { useT } from "@/i18n";
import { type ModelDraft } from "./constants";
import { ModelFormModal } from "./ModelFormModal";
import { ModelRow } from "./ModelRow";

interface ModelListCardProps {
  provider: ProviderWithModels;
  kind: ModelKind;
  models: ModelProfile[];
  editingModelId: number | null;
  addingModel: boolean;
  draft: ModelDraft;
  setDraft: Dispatch<SetStateAction<ModelDraft>>;
  saving: boolean;
  testingId: number | null;
  catalog: import("@/types").ChannelModelCatalog | null;
  catalogLoading: boolean;
  onFetchCatalog: () => void;
  onSave: (providerId: number) => void;
  onEdit: (m: ModelProfile) => void;
  onDelete: (model: ModelProfile) => void;
  onTest: (id: number) => void;
  onStartAdd: () => void;
  onCancelEdit: () => void;
  onCancelAdd: () => void;
}

/** Model-entry list for one provider channel (kind), with modal add/edit and test actions. */
export function ModelListCard(props: ModelListCardProps) {
  const {
    provider,
    kind,
    models,
    editingModelId,
    addingModel,
    draft,
    setDraft,
    saving,
    testingId,
    catalog,
    catalogLoading,
    onFetchCatalog,
    onSave,
    onEdit,
    onDelete,
    onTest,
    onStartAdd,
    onCancelEdit,
    onCancelAdd,
  } = props;
  const t = useT("settings");

  return (
    <div className="surface-card !p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-[13px] font-semibold text-ink">
          <Cpu size={14} className="text-[var(--primary)]" />
          {t("modelList.count", { count: models.length })}
        </h2>
        <button
          type="button"
          className="flex items-center gap-1 rounded-md border border-surface-border px-2 py-1 text-[11px] text-ink-muted transition-colors hover:border-[var(--primary)] hover:text-ink"
          onClick={onStartAdd}
        >
          <Plus size={12} /> {t("modelList.add")}
        </button>
      </div>

      <div className="space-y-2">
        {models.length === 0 && !addingModel && (
          <p className="text-[12px] text-ink-subtle">{t("modelList.emptyKind")}</p>
        )}
        {models.map((m) => (
          <ModelRow
            key={m.id}
            model={m}
            testing={testingId === m.id}
            onEdit={() => onEdit(m)}
            onDelete={() => onDelete(m)}
            onTest={() => onTest(m.id)}
          />
        ))}
        {addingModel && (
          <ModelFormModal
            draft={draft}
            setDraft={setDraft}
            catalog={catalog}
            catalogLoading={catalogLoading}
            onFetchCatalog={onFetchCatalog}
            onCancel={onCancelAdd}
            onSave={() => onSave(provider.id)}
            saving={saving}
          />
        )}
        {editingModelId != null && (
          <ModelFormModal
            titleKey="modelList.edit"
            draft={draft}
            setDraft={setDraft}
            catalog={catalog}
            catalogLoading={catalogLoading}
            onFetchCatalog={onFetchCatalog}
            onCancel={onCancelEdit}
            onSave={() => onSave(provider.id)}
            saving={saving}
          />
        )}
      </div>
    </div>
  );
}
