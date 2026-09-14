"use client";

/**
 * @file useDataClear
 * @description Destructive resume-collection clears for the settings data panel.
 *
 * Responsibilities:
 * - Track which clear is in flight so the panel can show a busy state
 * - Return the server-reported count so toasts can name it
 *
 * Must not own dialogs or toasts; the panel composes ConfirmDialog + Toast.
 */

import { useState } from "react";

import { resumeHttp } from "@/lib/api/clients";

export type DataClearKind = "results" | "collection";

export function useDataClear() {
  const [busy, setBusy] = useState<DataClearKind | null>(null);

  const run = async (kind: DataClearKind): Promise<number> => {
    setBusy(kind);
    try {
      if (kind === "results") return (await resumeHttp.clearReviewResults()).cleared;
      return (await resumeHttp.clearAllResumes()).deleted;
    } finally {
      setBusy(null);
    }
  };

  return { busy, run };
}
