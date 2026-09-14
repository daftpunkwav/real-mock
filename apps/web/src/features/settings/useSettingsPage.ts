"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "@/components/Toast";
import { getTranslator } from "@/i18n/resolve";
import { settingsHttp } from "@/lib/api/clients";
import type { ModelProfile, ProviderWithModels, TaskBindings } from "@/types";
import { EMPTY_DRAFT, type ModelDraft } from "./constants";
import { DEFAULT_MAX_OUTPUT_TOKENS } from "@/lib/llmDefaults";

/**
 * Owns settings-page state for providers, models, and task bindings.
 * This hook handles data loading and CRUD actions; feature components render the UI.
 */
export function useSettingsPage() {
  const [providers, setProviders] = useState<ProviderWithModels[]>([]);
  const [bindings, setBindings] = useState<TaskBindings | null>(null);
  const [selectedProviderId, setSelectedProviderId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);

  const [editingModelId, setEditingModelId] = useState<number | null>(null);
  const [draft, setDraft] = useState<ModelDraft>(EMPTY_DRAFT);
  const [addingModel, setAddingModel] = useState(false);

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
    setDraft(EMPTY_DRAFT);
  };

  const cancelEdit = () => {
    setEditingModelId(null);
    setDraft(EMPTY_DRAFT);
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
      setDraft(EMPTY_DRAFT);
      await reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("toast.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const deleteModel = async (id: number) => {
    const t = getTranslator("settings");
    try {
      await settingsHttp.deleteModel(id);
      toast.success(t("toast.deleted"));
      await reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("toast.deleteFailed"));
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
  };
}
