"use client";

/**
 * Models & handlers category: BYOK providers merging chat / stt / tts model types.
 * Left column lists configured providers plus a "+" add panel; the right side edits the
 * provider identity, the three channel tabs (connection settings per type), and each
 * type's model entries. Data lives in useSettingsPage.
 */

import { RefreshCw } from "lucide-react";
import { LoadError } from "@/components/LoadError";
import { BindingsCard } from "@/features/settings/BindingsCard";
import { ChannelCard } from "@/features/settings/ChannelCard";
import { ModelListCard } from "@/features/settings/ModelListCard";
import { ProviderCard } from "@/features/settings/ProviderCard";
import { ProviderList } from "@/features/settings/ProviderList";
import { useSettingsPage } from "@/features/settings/useSettingsPage";
import { channelForKind, KIND_META } from "@/features/settings/constants";
import { useT } from "@/i18n";

export function ModelsSettingsPanel() {
  const {
    providers,
    bindings,
    selectedProvider,
    selectedProviderId,
    setSelectedProviderId,
    selectedKind,
    switchKind,
    allModels,
    loading,
    loadError,
    saving,
    savingChannel,
    testingId,
    editingModelId,
    addingModel,
    draft,
    setDraft,
    catalog,
    catalogLoading,
    reload,
    openModelEdit,
    startAddModel,
    cancelEdit,
    saveModel,
    deleteModel,
    testModel,
    saveChannel,
    fetchCatalog,
    applyVendor,
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

  const channel = selectedProvider ? channelForKind(selectedProvider, selectedKind) : null;
  const kindModels = selectedProvider
    ? selectedProvider.models.filter((m) => m.kind === selectedKind)
    : [];

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr]">
      {/* Provider list + add panel */}
      <ProviderList
        providers={providers}
        selectedId={selectedProviderId}
        onSelect={(id) => {
          setSelectedProviderId(id);
          switchKind(selectedKind);
        }}
        onApplyVendor={applyVendor}
        onCreated={async (id) => {
          await reload();
          setSelectedProviderId(id);
        }}
      />

      {/* Provider identity + channel tabs + per-kind model list */}
      <div className="min-w-0 space-y-4">
        {selectedProvider ? (
          <>
            <ProviderCard provider={selectedProvider} onChanged={reload} />

            <div className="surface-card !p-4">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-[172px_1fr]">
                {/* Vertical kind rail */}
                <div className="flex flex-row flex-wrap gap-1 md:flex-col" role="tablist" aria-orientation="vertical">
                  {KIND_META.map(({ kind, labelKey }) => {
                    const count = selectedProvider.models.filter((m) => m.kind === kind).length;
                    const active = kind === selectedKind;
                    return (
                      <button
                        key={kind}
                        type="button"
                        role="tab"
                        aria-selected={active}
                        onClick={() => switchKind(kind)}
                        className={`flex min-w-0 flex-1 items-center justify-between gap-2 rounded-md border px-2.5 py-2 text-left text-[12px] transition-colors md:flex-none ${
                          active
                            ? "border-[var(--primary)] bg-[var(--info-soft)] text-ink"
                            : "border-transparent text-ink-muted hover:bg-surface-muted"
                        }`}
                      >
                        <span className="truncate">{t(labelKey)}</span>
                        <span className="shrink-0 rounded bg-surface-muted px-1.5 py-0.5 text-[10px] text-ink-subtle">
                          {count}
                        </span>
                      </button>
                    );
                  })}
                </div>

                {/* Selected kind: channel settings and model entries, single column */}
                <div className="min-w-0 space-y-4 md:border-l md:border-surface-border md:pl-4">
                  <ChannelCard
                    providerId={selectedProvider.id}
                    kind={selectedKind}
                    channel={channel}
                    showProtocol={selectedKind === "chat"}
                    onSave={saveChannel}
                    saving={savingChannel}
                  />

                  <div className="border-t border-surface-border pt-4">
                    <ModelListCard
                      provider={selectedProvider}
                      kind={selectedKind}
                      models={kindModels}
                      editingModelId={editingModelId}
                      addingModel={addingModel}
                      draft={draft}
                      setDraft={setDraft}
                      saving={saving}
                      testingId={testingId}
                      catalog={catalog}
                      catalogLoading={catalogLoading}
                      onFetchCatalog={() => fetchCatalog(selectedProvider.id, selectedKind)}
                      onSave={saveModel}
                      onEdit={openModelEdit}
                      onDelete={deleteModel}
                      onTest={testModel}
                      onStartAdd={startAddModel}
                      onCancelEdit={cancelEdit}
                      onCancelAdd={() => switchKind(selectedKind)}
                    />
                  </div>
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="surface-card p-6 text-center text-[13px] text-ink-muted">
            {t("provider.pickHint")}
          </div>
        )}

        {/* Task bindings */}
        <BindingsCard bindings={bindings} allModels={allModels} onUpdate={saveBinding} />
      </div>
    </div>
  );
}
