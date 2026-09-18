"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "@/components/Toast";
import { getTranslator } from "@/i18n/resolve";
import { settingsHttp } from "@/lib/api/clients";
import type {
  ChannelModelCatalog,
  ModelKind,
  ModelProfile,
  ProviderWithModels,
  TaskBindings,
} from "@/types";
import { emptyDraft, type ModelDraft } from "./constants";
import { DEFAULT_MAX_OUTPUT_TOKENS } from "@/lib/llmDefaults";

/**
 * Owns settings-page state for providers, channels, models, and task bindings.
 * One provider merges the chat / stt / tts model types; ``selectedKind`` is the active
 * channel tab whose connection settings and model entries are being edited.
 */
export function useSettingsPage() {
  const [providers, setProviders] = useState<ProviderWithModels[]>([]);
  const [bindings, setBindings] = useState<TaskBindings | null>(null);
  const [selectedProviderId, setSelectedProviderId] = useState<number | null>(null);
  const [selectedKind, setSelectedKind] = useState<ModelKind>("chat");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [saving, setSaving] = useState(false);
  const [savingChannel, setSavingChannel] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);

  const [editingModelId, setEditingModelId] = useState<number | null>(null);
  const [draft, setDraft] = useState<ModelDraft>(() => emptyDraft("chat"));
  const [addingModel, setAddingModel] = useState(false);
  const [catalog, setCatalog] = useState<ChannelModelCatalog | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);

  const selectedProvider = useMemo(
    () => providers.find((p) => p.id === selectedProviderId) ?? null,
    [providers, selectedProviderId],
  );
  const allModels = useMemo(() => providers.flatMap((p) => p.models), [providers]);

  const reload = useCallback(async () => {
    // Resolve at call time so locale changes are reflected inside this stable callback.
    const t = getTranslator("settings");
    setLoading(true);
    setLoadError("");
    try {
      const [provRes, bindRes] = await Promise.all([
        settingsHttp.listProviders(),
        settingsHttp.getBindings().catch(() => null),
      ]);
      const list = Array.isArray(provRes?.providers) ? provRes.providers : [];
      setProviders(list);
      if (bindRes) setBindings(bindRes);
      setSelectedProviderId((cur) =>
        cur && list.some((p) => p.id === cur) ? cur : (list[0]?.id ?? null),
      );
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : t("toast.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const switchKind = (kind: ModelKind) => {
    setSelectedKind(kind);
    setEditingModelId(null);
    setAddingModel(false);
    setDraft(emptyDraft(kind));
    setCatalog(null);
  };

  const openModelEdit = (m: ModelProfile) => {
    setEditingModelId(m.id);
    setAddingModel(false);
    setDraft({
      model: m.model,
      display_name: m.display_name || "",
      context_window: String(m.context_window || ""),
      max_output: String(m.max_output || ""),
      capabilities: { ...m.capabilities },
      extras_text: m.extras && Object.keys(m.extras).length ? JSON.stringify(m.extras, null, 2) : "",
    });
  };

  const startAddModel = () => {
    setAddingModel(true);
    setEditingModelId(null);
    setDraft(emptyDraft(selectedKind));
    setCatalog(null);
  };

  const cancelEdit = () => {
    setEditingModelId(null);
    setDraft(emptyDraft(selectedKind));
  };

  const draftFromForm = () => {
    const t = getTranslator("settings");
    let extras: Record<string, unknown> = {};
    if (draft.extras_text.trim()) {
      try {
        extras = JSON.parse(draft.extras_text);
      } catch {
        toast.error(t("toast.extrasInvalidJson"));
        return null;
      }
    }
    return {
      model: draft.model.trim(),
      kind: selectedKind,
      display_name: draft.display_name.trim(),
      context_window: Number(draft.context_window) || 0,
      max_output: Number(draft.max_output) || DEFAULT_MAX_OUTPUT_TOKENS,
      capabilities: draft.capabilities,
      extras,
    };
  };

  const saveModel = async (providerId: number) => {
    const t = getTranslator("settings");
    const body = draftFromForm();
    if (!body) return;
    if (!body.model) {
      toast.error(t("toast.modelNameRequired"));
      return;
    }
    setSaving(true);
    try {
      if (editingModelId) {
        await settingsHttp.updateModel(editingModelId, body);
        toast.success(t("toast.modelUpdated"));
      } else {
        await settingsHttp.createModel(providerId, body);
        toast.success(t("toast.modelAdded"));
      }
      setEditingModelId(null);
      setAddingModel(false);
      setDraft(emptyDraft(selectedKind));
      await reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("toast.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  /** Returns true when the model was actually deleted (caller owns the confirm step). */
  const deleteModel = async (id: number) => {
    const t = getTranslator("settings");
    try {
      await settingsHttp.deleteModel(id);
      toast.success(t("toast.deleted"));
      await reload();
      return true;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("toast.deleteFailed"));
      return false;
    }
  };

  const testModel = async (id: number) => {
    const t = getTranslator("settings");
    setTestingId(id);
    try {
      const res = await settingsHttp.testModel(id);
      if (res.success) toast.success(res.message || t("toast.testPassed"));
      else toast.warning(res.message || t("toast.testNotPassed"));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("toast.testFailed"));
    } finally {
      setTestingId(null);
    }
  };

  const saveChannel = async (
    providerId: number,
    kind: ModelKind,
    data: { api_base: string; full_url: boolean; protocol?: string; api_key?: string },
  ) => {
    const t = getTranslator("settings");
    setSavingChannel(true);
    try {
      await settingsHttp.updateChannel(providerId, kind, {
        ...data,
        protocol: data.protocol as import("@/types").LLMProtocol | undefined,
      });
      toast.success(t("channelCard.saved"));
      await reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("channelCard.saveFailed"));
    } finally {
      setSavingChannel(false);
    }
  };

  const fetchCatalog = async (providerId: number, kind: ModelKind) => {
    const t = getTranslator("settings");
    setCatalogLoading(true);
    try {
      const res = await settingsHttp.fetchChannelCatalog(providerId, kind);
      setCatalog(res);
    } catch (e) {
      setCatalog(null);
      toast.error(e instanceof Error ? e.message : t("catalog.loadFailed"));
    } finally {
      setCatalogLoading(false);
    }
  };

  const applyVendor = async (vendorId: string) => {
    const t = getTranslator("settings");
    try {
      const res = await settingsHttp.applyVendor(vendorId);
      await reload();
      setSelectedProviderId(res.provider_id);
      switchKind("chat");
      toast.success(
        t("recommended.applied").replace("{provider}", res.name),
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("recommended.addFailed"));
    }
  };

  const saveBinding = async (task: "chat" | "stt" | "tts", profileId: number) => {
    const t = getTranslator("settings");
    try {
      const res = await settingsHttp.updateBinding(task, { profile_id: profileId });
      setBindings(res);
      toast.success(t("toast.bindingUpdated"));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("toast.saveFailed"));
    }
  };

  return {
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
  };
}
