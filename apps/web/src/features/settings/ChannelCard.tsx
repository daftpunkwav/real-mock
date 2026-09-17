"use client";

/** Per-kind channel form: Base URL / full-URL flag / API key (API format on the chat tab
 * only — voice adapters route by vendor, not protocol). Voice channels are always full
 * URLs, so the flag is a chat-only toggle and stt/tts always save full_url=true.
 * Saving upserts the channel. */

import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { Select } from "@/components/Select";
import { useT } from "@/i18n";
import type { LLMProtocol, ModelKind, ProviderChannel } from "@/types";
import { PROTOCOL_OPTIONS } from "./constants";

export function ChannelCard({
  providerId,
  kind,
  channel,
  showProtocol,
  onSave,
  saving,
}: {
  providerId: number;
  kind: ModelKind;
  /** Null when this provider has no channel of the kind yet; saving creates it. */
  channel: ProviderChannel | null;
  showProtocol: boolean;
  onSave: (
    providerId: number,
    kind: ModelKind,
    data: { api_base: string; full_url: boolean; protocol?: string; api_key?: string },
  ) => Promise<void>;
  saving: boolean;
}) {
  const [apiBase, setApiBase] = useState(channel?.api_base ?? "");
  const [fullUrl, setFullUrl] = useState(channel?.full_url ?? false);
  const [protocol, setProtocol] = useState<LLMProtocol>(channel?.protocol ?? "openai_chat");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const t = useT("settings");
  // Voice endpoints are nonstandard, so stt/tts URLs are always complete.
  const fullUrlToggle = kind === "chat";
  const effectiveFullUrl = fullUrlToggle ? fullUrl : true;

  useEffect(() => {
    setApiBase(channel?.api_base ?? "");
    setFullUrl(channel?.full_url ?? false);
    setProtocol(channel?.protocol ?? "openai_chat");
    setApiKey("");
  }, [providerId, kind, channel?.api_base, channel?.full_url, channel?.protocol, channel?.has_api_key]);

  const save = () => onSave(providerId, kind, {
    api_base: apiBase,
    full_url: effectiveFullUrl,
    ...(showProtocol ? { protocol } : {}),
    ...(apiKey ? { api_key: apiKey } : {}),
  });

  return (
    <div className="grid grid-cols-1 gap-3">
      <div>
        <div className="mb-1 flex items-center gap-3">
          <span className="text-[11px] text-ink-muted">{t("providerCard.baseUrl.label")}</span>
          {fullUrlToggle && (
            <label className="flex cursor-pointer items-center gap-1 text-[11px] text-ink-muted">
              <input type="checkbox" checked={fullUrl} onChange={(e) => setFullUrl(e.target.checked)} />
              {t("providerCard.fullUrl.label")}
            </label>
          )}
        </div>
        <input
          className="field-input !h-9"
          value={apiBase}
          placeholder={effectiveFullUrl ? "https://…/v1/endpoint" : "https://…"}
          onChange={(e) => setApiBase(e.target.value)}
        />
      </div>
      {showProtocol && (
        <div>
          <label className="mb-1 block text-[11px] text-ink-muted">{t("providerCard.apiFormat.label")}</label>
          <Select
            className="!h-9"
            ariaLabel={t("providerCard.apiFormat.label")}
            value={protocol}
            options={PROTOCOL_OPTIONS}
            onChange={setProtocol}
            disabled={effectiveFullUrl}
          />
          {effectiveFullUrl && <p className="mt-1 text-[11px] text-ink-subtle">{t("providerCard.apiFormat.disabledHint")}</p>}
        </div>
      )}
      <div>
        <label className="mb-1 block text-[11px] text-ink-muted">
          {t("providerCard.apiKey.label")}
          {channel?.has_api_key ? t("providerCard.apiKey.setHint") : ""}
        </label>
        <div className="flex gap-1.5">
          <input
            className="field-input !h-9 flex-1"
            type={showKey ? "text" : "password"}
            value={apiKey}
            placeholder={channel?.has_api_key ? "••••••••" : "sk-…"}
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
      <div className="flex justify-end">
        <button type="button" className="btn-primary !h-8" onClick={save} disabled={saving}>
          <Save size={13} /> {saving ? t("channelCard.saving") : t("channelCard.save")}
        </button>
      </div>
    </div>
  );
}
