"use client";

/** Recommended (adapted) vendors: two-level cascade — level 1 vendor, level 2 model type.
 *
 * One click creates the provider shell (named after the catalog provider id, with the
 * recommended Base URL) plus a model entry with the recommended defaults; the user only
 * fills the API Key afterwards.
 */

import { useState } from "react";
import { ChevronDown, ChevronRight, Plus, Sparkles } from "lucide-react";
import { settingsHttp } from "@/lib/api/clients";
import { toast } from "@/components/Toast";
import { useT } from "@/i18n";
import type {
  ModelCapabilities,
  ProviderWithModels,
  RecommendedVendor,
  RecommendedVendorCapability,
} from "@/types";

const CAP_KEYS = ["reasoning", "recognize", "speak"] as const;
type CapKey = (typeof CAP_KEYS)[number];

/** Capability bits declared on the model entry created for each model type. */
const CAPABILITY_CAPS: Record<CapKey, Partial<ModelCapabilities>> = {
  reasoning: { chat: true },
  recognize: { audio_input: true },
  speak: { audio_output: true },
};

export function RecommendedVendors({
  providers,
  onChanged,
  onSelect,
}: {
  providers: ProviderWithModels[];
  onChanged: () => Promise<void>;
  onSelect: (id: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [vendors, setVendors] = useState<RecommendedVendor[] | null>(null);
  const [vendorId, setVendorId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);
  const t = useT("settings");

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && vendors === null) {
      setLoading(true);
      try {
        const res = await settingsHttp.listRecommendedVendors();
        setVendors(Array.isArray(res?.vendors) ? res.vendors : []);
      } catch {
        toast.error(t("recommended.loadFailed"));
      } finally {
        setLoading(false);
      }
    }
  };

  /** Reuse the provider shell when its canonical name exists; never overwrite user config. */
  const add = async (
    vendor: RecommendedVendor,
    capKey: CapKey,
    cap: RecommendedVendorCapability,
  ) => {
    if (!cap.default_model) {
      toast.error(t("recommended.noDefaultModel"));
      return;
    }
    setAdding(`${vendor.id}:${capKey}`);
    try {
      const existing = providers.find(
        (p) => p.name.toLowerCase() === cap.provider_id.toLowerCase(),
      );
      const providerId = existing
        ? existing.id
        : (
            await settingsHttp.createProvider({
              name: cap.provider_id,
              api_base: cap.default_api_base || "",
              protocol: "openai_chat",
              enabled: true,
            })
          ).id;
      await settingsHttp.createModel(providerId, {
        model: cap.default_model,
        display_name: "",
        capabilities: CAPABILITY_CAPS[capKey],
        extras: {},
        enabled: true,
      });
      toast.success(
        t("recommended.added")
          .replace("{model}", cap.default_model)
          .replace("{provider}", cap.provider_id),
      );
      await onChanged();
      onSelect(providerId);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("recommended.addFailed"));
    } finally {
      setAdding(null);
    }
  };

  const vendor = vendors?.find((v) => v.id === vendorId) ?? null;

  return (
    <div className="mt-3 border-t border-surface-border pt-3">
      <button
        type="button"
        className="flex w-full items-center gap-1.5 px-1 text-[11px] text-ink-muted hover:text-ink"
        onClick={toggle}
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <Sparkles size={12} className="text-[var(--primary)]" />
        {t("recommended.title")}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {loading && <p className="px-1 text-[11px] text-ink-subtle">{t("page.loading")}</p>}
          {!loading && vendors?.length === 0 && (
            <p className="px-1 text-[11px] text-ink-subtle">{t("recommended.empty")}</p>
          )}
          <div className="flex flex-wrap gap-1.5">
            {(vendors ?? []).map((v) => (
              <button
                key={v.id}
                type="button"
                onClick={() => setVendorId(v.id)}
                className={`rounded-md border px-2 py-1 text-[11px] transition-colors ${
                  v.id === vendorId
                    ? "border-[var(--primary)] bg-[var(--info-soft)] text-ink"
                    : "border-surface-border text-ink-muted hover:bg-surface-muted"
                }`}
              >
                {v.label}
              </button>
            ))}
          </div>
          {vendor && (
            <div className="space-y-1">
              <p className="px-1 text-[11px] text-ink-subtle">{t("recommended.hint")}</p>
              {CAP_KEYS.filter((k) => vendor.capabilities[k]).map((k) => {
                const cap = vendor.capabilities[k]!;
                return (
                  <div
                    key={k}
                    className="flex items-center gap-2 rounded-md border border-surface-border px-2 py-1.5"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[12px] text-ink">
                        {t(`recommended.cap.${k}` as const)}
                        {cap.adapted && (
                          <span className="ml-1.5 rounded bg-[var(--info-soft)] px-1 py-0.5 text-[10px] text-[var(--primary)]">
                            {t("recommended.adapted")}
                          </span>
                        )}
                      </p>
                      <p className="truncate text-[10px] text-ink-subtle">
                        {cap.default_model || cap.catalog_label}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="btn-primary !h-7 shrink-0 gap-1 !px-2 text-[11px]"
                      disabled={adding !== null}
                      onClick={() => add(vendor, k, cap)}
                    >
                      <Plus size={12} />
                      {adding === `${vendor.id}:${k}` ? t("recommended.adding") : t("recommended.add")}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
