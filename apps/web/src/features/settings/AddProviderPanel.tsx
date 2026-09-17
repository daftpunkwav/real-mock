"use client";

/** Add-provider panel: adapted vendors (one click provisions all three channels) plus a
 * custom free-name entry for BYOK vendors without a catalog row. */

import { useEffect, useState } from "react";
import { Sparkles, X } from "lucide-react";
import { settingsHttp } from "@/lib/api/clients";
import { toast } from "@/components/Toast";
import { useT } from "@/i18n";
import type { RecommendedVendor } from "@/types";

export function AddProviderPanel({
  onClose,
  onApplyVendor,
  onCreated,
}: {
  onClose: () => void;
  /** Hook-provisioned vendor apply: reloads, selects the provider, toasts. */
  onApplyVendor: (vendorId: string) => Promise<void>;
  /** Reloads and selects a freshly created custom provider. */
  onCreated: (providerId: number) => Promise<void>;
}) {
  const [vendors, setVendors] = useState<RecommendedVendor[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState<string | null>(null);
  const [customName, setCustomName] = useState("");
  const t = useT("settings");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    settingsHttp
      .listRecommendedVendors()
      .then((res) => {
        if (!cancelled) setVendors(Array.isArray(res?.vendors) ? res.vendors : []);
      })
      .catch(() => {
        if (!cancelled) toast.error(t("recommended.loadFailed"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const apply = async (vendor: RecommendedVendor) => {
    setApplying(vendor.id);
    try {
      await onApplyVendor(vendor.id);
      onClose();
    } finally {
      setApplying(null);
    }
  };

  const createCustom = async () => {
    const name = customName.trim();
    if (!name) return;
    setApplying("__custom__");
    try {
      const res = await settingsHttp.createProvider({
        name,
        channels: [{ kind: "chat" }],
      });
      setCustomName("");
      await onCreated(res.id);
      onClose();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t("providerList.createFailed"));
    } finally {
      setApplying(null);
    }
  };

  return (
    <div className="mt-3 border-t border-surface-border pt-3">
      <div className="mb-2 flex items-center gap-1.5 px-1">
        <Sparkles size={12} className="text-[var(--primary)]" />
        <p className="text-[11px] text-ink-muted">{t("recommended.title")}</p>
        <div className="flex-1" />
        <button
          type="button"
          className="rounded p-0.5 text-ink-subtle hover:text-ink"
          aria-label={t("recommended.close")}
          onClick={onClose}
        >
          <X size={12} />
        </button>
      </div>
      {loading && <p className="px-1 text-[11px] text-ink-subtle">{t("page.loading")}</p>}
      {!loading && vendors?.length === 0 && (
        <p className="px-1 text-[11px] text-ink-subtle">{t("recommended.empty")}</p>
      )}
      <div className="flex flex-wrap gap-1.5">
        {(vendors ?? []).map((v) => (
          <button
            key={v.id}
            type="button"
            disabled={applying !== null}
            className={`rounded-md border px-2 py-1 text-[11px] transition-colors disabled:opacity-50 ${
              applying === v.id
                ? "border-[var(--primary)] bg-[var(--info-soft)] text-ink"
                : "border-surface-border text-ink-muted hover:bg-surface-muted"
            }`}
            title={t("recommended.applyHint")}
            onClick={async () => {
              await apply(v);
            }}
          >
            {applying === v.id ? t("recommended.adding") : v.label}
          </button>
        ))}
      </div>
      <p className="mt-2 px-1 text-[10px] leading-relaxed text-ink-subtle">{t("recommended.hint")}</p>

      <div className="mt-3 flex gap-1.5">
        <input
          className="field-input !h-8 flex-1 text-[12px]"
          placeholder={t("providerList.namePlaceholder")}
          value={customName}
          onChange={(e) => setCustomName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") createCustom();
          }}
        />
        <button
          type="button"
          className="btn-primary !h-8 shrink-0 !px-2.5 text-[11px]"
          disabled={!customName.trim() || applying !== null}
          onClick={createCustom}
        >
          {applying === "__custom__" ? t("recommended.adding") : t("providerList.createCustom")}
        </button>
      </div>
    </div>
  );
}
