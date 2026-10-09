"use client";

/**
 * @file WipeCard.tsx
 * @description Destructive wipe card: clears every interview artifact behind a
 * two-step confirmation (open + acknowledgement checkbox before confirm
 * unlocks).
 */

import { HardDriveDownload, TriangleAlert } from "lucide-react";
import { toast } from "@/components/Toast";
import { useT } from "@/i18n";
import { formatApiError } from "@/lib/api/base";
import { settingsHttp } from "@/lib/api/clients";
import { DangerActionCard } from "./DangerActionCard";

/** Wipe-everything card; onWiped lets the owner refetch any stale catalogs. */
export const WipeCard = ({ onWiped }: { onWiped: () => void }) => {
  const t = useT("settings");
  return (
    <DangerActionCard
      icon={<TriangleAlert size={16} className="text-[var(--danger)]" />}
      title={t("data.wipe.title")}
      description={t("data.wipe.desc")}
      actionLabel={t("data.wipe.action")}
      confirmTitle={t("data.wipe.confirmTitle")}
      confirmBody={t("data.wipe.confirmBody")}
      acknowledgementLabel={t("data.wipe.acknowledge")}
      actionIcon={<HardDriveDownload size={13} className="rotate-180" />}
      onConfirm={async () => {
        // Thrown errors keep the dialog open; the toast already fired.
        try {
          await settingsHttp.clearAllData();
          toast.success(t("data.wipe.done"));
          onWiped();
        } catch (err) {
          toast.error(err instanceof Error ? formatApiError(err) : t("data.wipe.failed"));
          throw err;
        }
      }}
    />
  );
};
