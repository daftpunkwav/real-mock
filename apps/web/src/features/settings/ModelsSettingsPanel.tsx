"use client";

/**
 * Models & handlers category: BYOK providers, model entries, and task bindings.
 * Data lives in useSettingsPage; feature components own list, form, and binding UI.
 */

import { RefreshCw } from "lucide-react";
import { LoadError } from "@/components/LoadError";
import { BindingsCard } from "@/features/settings/BindingsCard";
import { ModelListCard } from "@/features/settings/ModelListCard";
import { ProviderCard } from "@/features/settings/ProviderCard";
import { ProviderList } from "@/features/settings/ProviderList";
import { useSettingsPage } from "@/features/settings/useSettingsPage";
import { useT } from "@/i18n";

export function ModelsSettingsPanel() {
  const {
    providers,
    bindings,
    selectedProvider,
    selectedProviderId,
    setSelectedProviderId,
    allModels,
    loading,
    loadError,
    saving,
    testingId,
    editingModelId,
    addingModel,
    setAddingModel,
    draft,
    setDraft,
    reload,
    openModelEdit,
    startAddModel,
    cancelEdit,
    saveModel,
    deleteModel,
    testModel,
    saveBinding,
  } = useSettingsPage();
  const t = useT("settings");

  if (loading) {
    return (
      <div className="surface-card flex items-center justify-center p-10 text-sm text-ink-muted">
        <RefreshCw size={16} className="mr-2 animate-spin" /> {t("page.loading")}
      </div>
    );
  }
  if (loadError) {
    return <LoadError message={loadError} onRetry={reload} />;
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr]">
      {/* Provider list */}
      <ProviderList
        providers={providers}
        selectedId={selectedProviderId}
        onSelect={setSelectedProviderId}
        onChanged={reload}
      />

      {/* Provider editor and model list */}
      <div className="min-w-0 space-y-4">
        {selectedProvider ? (
          <ProviderCard provider={selectedProvider} onChanged={reload} />
        ) : (
          <div className="surface-card p-6 text-center text-[13px] text-ink-muted">
            {t("provider.pickHint")}
          </div>
        )}

        {selectedProvider && (
          <ModelListCard
            provider={selectedProvider}
            editingModelId={editingModelId}
            addingModel={addingModel}
            draft={draft}
            setDraft={setDraft}
            saving={saving}
            testingId={testingId}
            onSave={saveModel}
            onEdit={openModelEdit}
            onDelete={deleteModel}
            onTest={testModel}
            onStartAdd={startAddModel}
            onCancelEdit={cancelEdit}
            onCancelAdd={() => setAddingModel(false)}
          />
        )}

        {/* Task bindings */}
        <BindingsCard bindings={bindings} allModels={allModels} onUpdate={saveBinding} />
      </div>
    </div>
  );
}
