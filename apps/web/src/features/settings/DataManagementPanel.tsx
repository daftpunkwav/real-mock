"use client";

/**
 * @file DataManagementPanel.tsx
 * @description Data category composition point: owns the picker-catalog
 * loading shared by the export and wipe cards and lays them out. The export
 * implementation lives in ExportCard.tsx, the clear-data implementation in
 * WipeCard.tsx.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { recordsHttp, resumeHttp } from "@/lib/api/clients";
import type { ResumeResponse } from "@/lib/api/contract";
import type { SessionHistoryItem } from "@/types/domains/records";
import { ExportCard } from "./ExportCard";
import { WipeCard } from "./WipeCard";

/**
 * Fetch one catalog list under the given alive guard: null-safe rows on
 * success, an empty list on failure.
 */
const fetchCatalogList = async <T,>(
  alive: () => boolean,
  load: () => Promise<T[]>,
): Promise<T[]> => {
  try {
    const fetched = await load();
    return alive() && Array.isArray(fetched) ? fetched : [];
  } catch {
    return [];
  }
};

/** Panel root: loads the picker catalogs once and lays out the two cards. */
export const DataManagementPanel = () => {
  const [sessions, setSessions] = useState<SessionHistoryItem[] | null>(null);
  const [resumes, setResumes] = useState<ResumeResponse[] | null>(null);
  const [reloadSeq, setReloadSeq] = useState(0);

  const activeLoadCleanup = useRef<(() => void) | null>(null);
  const mounted = useRef(false);

  const loadItems = useCallback(() => {
    activeLoadCleanup.current?.();
    if (!mounted.current) return;
    let alive = true;
    const cancel = () => {
      alive = false;
    };
    activeLoadCleanup.current = cancel;
    void fetchCatalogList(
      () => alive,
      () => recordsHttp.listSessions(),
    ).then((rows) => {
      if (alive) setSessions(rows);
    });
    void fetchCatalogList(
      () => alive,
      () => resumeHttp.listResumes(),
    ).then((rows) => {
      if (alive) setResumes(rows);
    });
  }, []);

  useEffect(() => {
    mounted.current = true;
    loadItems();
    return () => {
      mounted.current = false;
      activeLoadCleanup.current?.();
    };
  }, [loadItems]);

  // A finished export or wipe bumps the sequence to refetch both catalogs:
  // the pickers then point at whatever actually survived.
  useEffect(() => {
    if (reloadSeq > 0) loadItems();
  }, [reloadSeq, loadItems]);

  // Null-safe list snapshots for the pickers.
  const sessionList = sessions ?? [];
  const resumeList = resumes ?? [];

  const bumpReload = () => setReloadSeq((n) => n + 1);

  return (
    <div className="space-y-4">
      <ExportCard sessions={sessionList} resumes={resumeList} onExported={bumpReload} />
      <WipeCard onWiped={bumpReload} />
    </div>
  );
};
