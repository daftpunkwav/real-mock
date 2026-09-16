"use client";

/** Base URL / / Key / Use / . */

import { useEffect, useState } from "react";
import { Save, Trash2 } from "lucide-react";
import { settingsHttp } from "@/lib/api/clients";
import { toast } from "@/components/Toast";
import { Select } from "@/components/Select";
import { useT } from "@/i18n";
import type { LLMProtocol, ProviderWithModels } from "@/types";
import { PROTOCOL_OPTIONS } from "./constants";

export function ProviderCard({
  provider,
  onChanged,
}: {
  provider: ProviderWithModels;
  onChanged: () => Promise<void>;
}) {
  const [name, setName] = useState(provider.name);
  const [apiBase, setApiBase] = useState(provider.api_base);
  const [fullUrl, setFullUrl] = useState(provider.full_url);
  const [protocol, setProtocol] = useState<LLMProtocol>(provider.protocol);
  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(provider.enabled);
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const t = useT("settings");

  useEffect(() => {
    setName(provider.name);
    setApiBase(provider.api_base);
    setFullUrl(provider.full_url);
    setProtocol(provider.protocol);
    setEnabled(provider.enabled);
    setApiKey("");
  }, [provider.id, provider.name, provider.api_base, provider.full_url, provider.protocol, provider.enabled]);

  const save = async () => {
    setSaving(true);
    try {
      await settingsHttp.updateProvider(provider.id, {
        name,
        api_base: apiBase,
        full_url: fullUrl,
        protocol,
        enabled,
        api_key: apiKey || undefined,
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
    try {
      await settingsHttp.deleteProvider(provider.id);
      toast.success(t("providerCard.deleted"));
      await onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("providerCard.deleteFailed"));
    }
  };

  return (
    <div className="surface-card !p-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">{t("providerCard.name.label")}</label>
          <input className="field-input !h-9" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <div className="mb-1 flex items-center gap-3">
            <span className="text-[11px] text-ink-muted">{t("providerCard.baseUrl.label")}</span>
            <label className="flex cursor-pointer items-center gap-1 text-[11px] text-ink-muted">
              <input type="checkbox" checked={fullUrl} onChange={(e) => setFullUrl(e.target.checked)} />
              {t("providerCard.fullUrl.label")}
            </label>
          </div>
          <input
            className="field-input !h-9"
            value={apiBase}
            placeholder={fullUrl ? "https://…/v1/endpoint" : "https://…"}
            onChange={(e) => setApiBase(e.target.value)}
          />
          {fullUrl && <p className="mt-1 text-[11px] text-ink-subtle">{t("providerCard.fullUrl.hint")}</p>}
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">{t("providerCard.apiFormat.label")}</label>
          <Select
            className="!h-9"
            ariaLabel={t("providerCard.apiFormat.label")}
            value={protocol}
            options={PROTOCOL_OPTIONS}
            onChange={setProtocol}
            disabled={fullUrl}
          />
          {fullUrl && <p className="mt-1 text-[11px] text-ink-subtle">{t("providerCard.apiFormat.disabledHint")}</p>}
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">
            {t("providerCard.apiKey.label")}
            {provider.has_api_key ? t("providerCard.apiKey.setHint") : ""}
          </label>
          <div className="flex gap-1.5">
            <input
              className="field-input !h-9 flex-1"
              type={showKey ? "text" : "password"}
              value={apiKey}
              placeholder={provider.has_api_key ? "••••••••" : "sk-…"}
              onChange={(e) => setApiKey(e.target.value)}
            />
            <button
              type="button"
              className="shrink-0 text-[11px] text-ink-subtle hover:text-ink"
              onClick={() => setShowKey((v) => !v)}
            >
              {showKey ? t("providerCard.hide") : t("providerCard.show")}
            </button>
          </div>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <label className="flex items-center gap-1.5 text-[12px] text-ink-muted">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          {t("providerCard.enabled")}
        </label>
        <div className="flex-1" />
        <button
          type="button"
          className="flex items-center gap-1 rounded-md border border-surface-border px-2.5 py-1.5 text-[12px] text-ink-muted transition-colors hover:border-[var(--danger)] hover:text-[var(--danger)]"
          onClick={remove}
        >
          <Trash2 size={13} /> {t("providerCard.delete")}
        </button>
        <button type="button" className="btn-primary !h-8" onClick={save} disabled={saving}>
          <Save size={13} /> {saving ? t("providerCard.saving") : t("providerCard.save")}
        </button>
      </div>
    </div>
  );
}
