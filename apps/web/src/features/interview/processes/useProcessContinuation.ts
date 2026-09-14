"use client";

/** Continue-process data domain: eligible multi-round processes + next-round creation. */

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getTranslator } from "@/i18n/resolve";
import { interviewHttp as api } from "@/lib/api/clients";
import { toast } from "@/components/Toast";
import { selectEligibleProcesses, type EligibleProcess } from "./eligibility";

export function useProcessContinuation() {
  const router = useRouter();
  const [processes, setProcesses] = useState<EligibleProcess[]>([]);
  const [loading, setLoading] = useState(true);
  const [startingId, setStartingId] = useState<number | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    api
      .listProcesses()
      .then((rows) => setProcesses(selectEligibleProcesses(rows)))
      .catch(() => setProcesses([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const startNext = async (process: EligibleProcess) => {
    const t = getTranslator("interview");
    setStartingId(process.id);
    try {
      const session = await api.createNextRound(process.id);
      router.push(`/interview/${session.id}`);
    } catch (e) {
      toast.error(
        e instanceof Error ? e.message : t("process.nextFailed"),
      );
      setStartingId(null);
    }
  };

  return { processes, loading, startingId, startNext, reload: load };
}
