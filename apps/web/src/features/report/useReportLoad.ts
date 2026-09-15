"use client";

/**
 * Report page load domain: get once, then live SSE while generating (agent
 * progress + done), poll fallback, ledger fallback via recordsHttp, and retry
 * through records debrief.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { recordsHttp, reportHttp } from "@/lib/api/clients";
import type { ReportStreamEvent } from "@/lib/api/reportHttp";
import { ApiError } from "@/lib/api/base";
import { getTranslator } from "@/i18n/resolve";
import {
  applyReportLiveEvent,
  emptyReportLiveState,
  type ReportLiveState,
} from "./liveEvents";
import type { DebriefReport, GetReportResponse } from "@/types/domains/report";
import type { LedgerDocument } from "@/types/domains/records";

function isReportPending(error: unknown): boolean {
  if (error instanceof ApiError) {
    if (error.code === "A2005") return false;
    return error.code === "A2004" || (error.retryable && error.code !== "C1001");
  }
  const msg = error instanceof Error ? error.message : String(error);
  // Code markers preferred; bilingual substrings cover legacy/non-ApiError fallbacks.
  if (/A2005|生成失败|generation failed/i.test(msg)) return false;
  return /尚未|A2004|not generated|not (?:yet )?ready/i.test(msg);
}

function isReportFailed(error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.code === "A2005" || error.code === "C1001";
  }
  const msg = error instanceof Error ? error.message : String(error);
  return /A2005|C1001|生成失败|generation failed/i.test(msg);
}

/**
 * Session not finished yet (A2003): the report page often loads milliseconds
 * after the closing speech while `run_finish_lifecycle` is still committing
 * in the background. Retry briefly as pending instead of erroring out; a
 * genuinely active session exhausts the cap and surfaces the real error.
 */
function isReportNotFinished(error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.code === "A2003";
  }
  const msg = error instanceof Error ? error.message : String(error);
  return /A2003|请先完成|not finished|finish the interview/i.test(msg);
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms);
    const onAbort = () => {
      window.clearTimeout(timer);
      reject(new DOMException("aborted", "AbortError"));
    };
    if (signal.aborted) {
      onAbort();
      return;
    }
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

function isValidSessionId(id: number): boolean {
  return Number.isFinite(id) && id > 0;
}

async function ensureLedger(
  id: number,
  data: GetReportResponse,
): Promise<LedgerDocument | null> {
  if (data.ledger?.turns && data.ledger.turns.length > 0) {
    return data.ledger;
  }
  try {
    return await recordsHttp.getLedger(id);
  } catch {
    return data.ledger ?? null;
  }
}

/** Report page load domain: invalid-id guard, A2004 poll, A2005 stop, retry. */
export function useReportLoad(sessionId: number) {
  const [report, setReport] = useState<DebriefReport | null>(null);
  const [ledger, setLedger] = useState<LedgerDocument | null>(null);
  const [status, setStatus] = useState<string | undefined>();
  const [duration, setDuration] = useState<number | undefined>();
  const [messagesCount, setMessagesCount] = useState<number | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [live, setLive] = useState<ReportLiveState>(emptyReportLiveState);
  const [generating, setGenerating] = useState(false);

  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;
  const seqRef = useRef(0);

  const applyPayload = async (data: GetReportResponse, id: number, seq: number) => {
    const nextLedger = await ensureLedger(id, data);
    if (seq !== seqRef.current || id !== sessionIdRef.current) return;
    setReport(data.report);
    setLedger(nextLedger);
    setStatus(data.status);
    setDuration(data.duration_minutes ?? undefined);
    setMessagesCount(data.messages_count ?? undefined);
  };

  // Bumped by retryGenerate to restart the full load (GET → SSE → poll).
  // The stream endpoint's upsert_pending already resets failed rows to pending,
  // so no separate sync retry call is needed (it would block up to 180s while
  // the agent budget is 480s, and aborting it strands the row as generating).
  const [loadTick, setLoadTick] = useState(0);

  const retryGenerate = useCallback(() => {
    const id = sessionIdRef.current;
    if (!isValidSessionId(id)) return;
    setLoadTick((t) => t + 1);
  }, []);

  useEffect(() => {
    const seq = ++seqRef.current;
    if (!isValidSessionId(sessionId)) {
      setReport(null);
      setLedger(null);
      setError(getTranslator("report")("errors.invalidSession"));
      setLoading(false);
      return;
    }
    const ac = new AbortController();
    setLoading(true);
    setError("");
    setReport(null);
    setLedger(null);

    const poll = async () => {
      // Report generation takes minutes (agent budget 480s): poll ~5 minutes
      // before surfacing notGenerated. The live progress view stays up while
      // generating is true (see page.tsx).
      setGenerating(true);
      const maxAttempts = 60;
      for (let attempt = 0; attempt < maxAttempts; attempt++) {
        if (ac.signal.aborted || seq !== seqRef.current) return;
        try {
          const data = await reportHttp.getReport(sessionId);
          if (ac.signal.aborted || seq !== seqRef.current) return;
          await applyPayload(data, sessionId, seq);
          setError("");
          setLoading(false);
          setGenerating(false);
          return;
        } catch (e) {
          if (ac.signal.aborted || seq !== seqRef.current) return;
          if (isReportFailed(e)) {
            setError(
              e instanceof Error
                ? e.message
                : getTranslator("report")("errors.generateFailed"),
            );
            setLoading(false);
            setGenerating(false);
            return;
          }
          // A2003 right after finish is a commit race (finish_lifecycle still
          // running in the background): retry briefly, then surface the error
          // so genuinely active sessions still get the real message.
          if (isReportNotFinished(e) && attempt >= 10) {
            setError(e instanceof Error ? e.message : String(e));
            setLoading(false);
            setGenerating(false);
            return;
          }
          if (isReportPending(e) || isReportNotFinished(e)) {
            try {
              await sleep(Math.min(1000 * (attempt + 1), 5000), ac.signal);
            } catch {
              return;
            }
            continue;
          }
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
          setGenerating(false);
          return;
        }
      }
      if (!ac.signal.aborted && seq === seqRef.current) {
        setError(getTranslator("report")("errors.notGenerated"));
        setLoading(false);
        setGenerating(false);
      }
    };

    /** Live generation path: SSE progress events, full report on done. */
    const liveStream = () =>
      new Promise<void>((resolve) => {
        if (ac.signal.aborted) return resolve();
        setGenerating(true);
        setLive(emptyReportLiveState());
        const onEvent = (event: ReportStreamEvent) => {
          if (ac.signal.aborted || seq !== seqRef.current) return;
          if (event.type === "done" && event.report) {
            void applyPayload(
              {
                session_id: sessionId,
                report: event.report,
                messages_count: 0,
                status: "ready",
              },
              sessionId,
              seq,
            );
            setError("");
            setLoading(false);
            setGenerating(false);
            resolve();
            return;
          }
          if (event.type === "error") {
            setError(event.message || getTranslator("report")("errors.generateFailed"));
            setLoading(false);
            setGenerating(false);
            resolve();
            return;
          }
          setLive((prev) => applyReportLiveEvent(prev, event));
        };
        reportHttp
          .streamReport(sessionId, onEvent)
          .then(() => {
            // Stream ended without done/error: keep the live progress view up
            // while the poll fallback waits (poll owns generating from here).
            if (!ac.signal.aborted && seq === seqRef.current) {
              void poll();
            }
            resolve();
          })
          .catch(() => {
            if (!ac.signal.aborted && seq === seqRef.current) {
              void poll();
            }
            resolve();
          });
      });

    const bootstrap = async () => {
      // Fast path: already ready.
      try {
        const data = await reportHttp.getReport(sessionId);
        if (ac.signal.aborted || seq !== seqRef.current) return;
        await applyPayload(data, sessionId, seq);
        setLoading(false);
        return;
      } catch (e) {
        if (ac.signal.aborted || seq !== seqRef.current) return;
        if (isReportFailed(e)) {
          setError(
            e instanceof Error ? e.message : getTranslator("report")("errors.generateFailed"),
          );
          setLoading(false);
          return;
        }
        if (!isReportPending(e) && !isReportNotFinished(e)) {
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
          return;
        }
      }
      // Pending (or finish-commit race) → live generation stream (poll fallback inside).
      await liveStream();
    };

    void bootstrap();
    return () => {
      ac.abort();
    };
  }, [sessionId, loadTick]);

  return {
    report,
    ledger,
    status,
    duration,
    messagesCount,
    loading,
    error,
    generating,
    live,
    retryGenerate,
  };
}
