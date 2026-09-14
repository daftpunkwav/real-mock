/**
 * @file resumeHttp
 * @description REST client for the resume resource (`/v1/resume`).
 *
 * Responsibilities:
 * - Upload / list / activate / delete / analyze / original-file preview URLs
 * - Reject empty 200 JSON bodies so callers never treat `undefined` as a list
 * - Forward AbortSignal for list cancellation
 *
 * Must not own list selection, analysis formatting, or UI state.
 *
 * Path convention (same as other domain clients):
 * - JSON calls use `request("/v1/...")`; `request()` prefixes `/api` itself.
 * - Multipart, raw `fetch`, and `<img>` URLs use `resolveBackendUrl("/api/v1/...")`
 *   because they cannot go through `request()` (that helper forces JSON
 *   Content-Type and parses a JSON body).
 */

import type { ResumeAnalysis, ResumeResponse } from "@/lib/api/contract";
import { getLocale } from "@/i18n/resolve";
import {
  ANALYZE_TIMEOUT_MS,
  ApiError,
  consumeSSE,
  parseStructuredErrorResponse,
  request,
  resolveBackendUrl,
} from "@/lib/api/base";
import type { ResumeAnalyzeSSEEvent } from "@/lib/api/resumeAnalyzeEvents";

/** 3x the backend SSE heartbeat (15s): stall longer than this and the stream is dead. */
const SSE_IDLE_TIMEOUT_MS = 45_000;

/** Multipart uploads bypass request(): bound slow networks so the UI never hangs forever. */
const UPLOAD_TIMEOUT_MS = 180_000;

function expectBody<T>(data: T, message: string): T {
  if (data === undefined || data === null) {
    throw new ApiError(message, 0, { code: "NET0003" });
  }
  return data;
}

async function readJsonBody<T>(res: Response, emptyMessage: string): Promise<T> {
  const text = await res.text();
  if (!text) throw new ApiError(emptyMessage, res.status, { code: "NET0003" });
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError("Server returned invalid JSON", res.status, { code: "NET0004" });
  }
}

export const resumeHttp = {
  uploadResume: async (file: File): Promise<ResumeResponse> => {
    const url = resolveBackendUrl("/api/v1/resume/upload");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);
    let res: Response;
    try {
      const form = new FormData();
      form.append("file", file);
      res = await fetch(url, {
        method: "POST",
        body: form,
        credentials: "include",
        signal: controller.signal,
      });
    } catch {
      if (controller.signal.aborted) {
        throw new ApiError(
          `Request timed out (${UPLOAD_TIMEOUT_MS / 1000}s). The upload is slow; retry on a better network`,
          0,
          { code: "NET0001", params: { seconds: UPLOAD_TIMEOUT_MS / 1000 } },
        );
      }
      throw new ApiError("Cannot reach the backend", 0, { code: "NET0000", params: { url } });
    } finally {
      clearTimeout(timer);
    }
    if (!res.ok) {
      const error = await parseStructuredErrorResponse(res);
      throw new ApiError(error.message, res.status, error);
    }
    return readJsonBody<ResumeResponse>(res, "Failed to upload resume: server returned an empty response");
  },
  uploadVersion: async (resumeId: number, file: File): Promise<ResumeResponse> => {
    const url = resolveBackendUrl(`/api/v1/resume/${resumeId}/versions`);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);
    let res: Response;
    try {
      const form = new FormData();
      form.append("file", file);
      res = await fetch(url, {
        method: "POST",
        body: form,
        credentials: "include",
        signal: controller.signal,
      });
    } catch {
      if (controller.signal.aborted) {
        throw new ApiError(
          `Request timed out (${UPLOAD_TIMEOUT_MS / 1000}s). The upload is slow; retry on a better network`,
          0,
          { code: "NET0001", params: { seconds: UPLOAD_TIMEOUT_MS / 1000 } },
        );
      }
      throw new ApiError("Cannot reach the backend", 0, { code: "NET0000", params: { url } });
    } finally {
      clearTimeout(timer);
    }
    if (!res.ok) {
      const error = await parseStructuredErrorResponse(res);
      throw new ApiError(error.message, res.status, error);
    }
    return readJsonBody<ResumeResponse>(res, "Failed to upload resume version: server returned an empty response");
  },
  listResumes: async (options?: { signal?: AbortSignal }) =>
    expectBody(
      await request<ResumeResponse[]>("/v1/resume/list", { signal: options?.signal }),
      "Failed to load resumes: server returned an empty response",
    ),
  getLimits: async (options?: { signal?: AbortSignal }) =>
    expectBody(
      await request<import("@/lib/api/contract").ResumeDomainLimits>("/v1/resume/limits", {
        signal: options?.signal,
      }),
      "Failed to load resume limits: server returned an empty response",
    ),
  /** Original resume file URL: inline preview by default; ``download=true`` forces attachment. */
  resumeFileUrl: (id: number, download = false) =>
    resolveBackendUrl(resumeHttp.resumeFilePath(id, download)),
  /** Path-only variant for hydration-safe rendering (see ``useAlignedBackendUrl``). */
  resumeFilePath: (id: number, download = false) =>
    `/api/v1/resume/${id}/file${download ? "?download=1" : ""}`,
  /** Original resume text (txt/md online preview); error semantics match other endpoints. */
  resumeFileText: async (id: number): Promise<string> => {
    const url = resolveBackendUrl(`/api/v1/resume/${id}/file`);
    let res: Response;
    try {
      res = await fetch(url, {
        credentials: "include",
      });
    } catch {
      throw new ApiError("Cannot reach the backend", 0, { code: "NET0000", params: { url } });
    }
    if (!res.ok) {
      const error = await parseStructuredErrorResponse(res);
      throw new ApiError(error.message, res.status, error);
    }
    return res.text();
  },
  /** Paginated preview meta (PDF page count; other formats return pages=0). */
  resumePagesMeta: async (id: number) =>
    expectBody(
      await request<{ pages: number }>(`/v1/resume/${id}/pages`),
      "Failed to load resume pages: server returned an empty response",
    ),
  /** Server-rendered single-page PNG URL (1-based page), for direct <img> use. */
  resumePageImageUrl: (id: number, page: number) =>
    resolveBackendUrl(resumeHttp.resumePageImagePath(id, page)),
  /** Path-only variant for hydration-safe rendering (see ``useAlignedBackendUrl``). */
  resumePageImagePath: (id: number, page: number) =>
    `/api/v1/resume/${id}/pages/${page}`,
  activateResume: async (id: number, options?: { signal?: AbortSignal }) =>
    expectBody(
      await request<ResumeResponse>(`/v1/resume/${id}/activate`, {
        method: "POST",
        signal: options?.signal,
      }),
      "Failed to activate resume: server returned an empty response",
    ),
  deleteResume: async (id: number) =>
    expectBody(
      await request<{ ok: boolean; id: number }>(`/v1/resume/${id}`, { method: "DELETE" }),
      "Failed to delete resume: server returned an empty response",
    ),
  /** Wipe deep-review results for every resume; files and rows stay. */
  clearReviewResults: async () =>
    expectBody(
      await request<{ ok: boolean; cleared: number }>(`/v1/resume/analyses`, {
        method: "DELETE",
      }),
      "Failed to clear review results: server returned an empty response",
    ),
  /** Delete every resume row and its files; review history goes with the rows. */
  clearAllResumes: async () =>
    expectBody(
      await request<{ ok: boolean; deleted: number }>(`/v1/resume/collection`, {
        method: "DELETE",
      }),
      "Failed to delete all resumes: server returned an empty response",
    ),
  /**
   * Persisted analysis for this resume. The page still reloads the list so
   * collection state picks up `score` / `analysis`; callers should not render
   * this payload as a substitute for the list row.
   */
  analyzeResume: async (id: number) =>
    expectBody(
      await request<ResumeAnalysis>(`/v1/resume/${id}/analyze`, {
        method: "POST",
        body: JSON.stringify({ locale: getLocale() }),
        timeoutMs: ANALYZE_TIMEOUT_MS,
      }),
      "Failed to analyze resume: server returned an empty response",
    ),
  /**
   * Streaming deep review. Emits live plan / tool / thinking events; the
   * ``done`` event carries the persisted ``ResumeAnalysis``.
   *
   * A half-open connection with no bytes for SSE_IDLE_TIMEOUT_MS aborts as
   * NET0001 so the user can retry manually; heartbeat comments count as
   * liveness, so only a truly stalled stream is killed. Automatic reconnect
   * is deliberately not attempted (a retried Agent loop would bill twice).
   */
  analyzeResumeStream: async (
    id: number,
    onEvent?: (event: ResumeAnalyzeSSEEvent) => void,
  ): Promise<ResumeAnalysis> => {
    const url = resolveBackendUrl(`/api/v1/resume/${id}/analyze/stream`);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ANALYZE_TIMEOUT_MS);
    let idleTimedOut = false;
    let lastEventAt = Date.now();
    const idleTimer = setInterval(() => {
      if (Date.now() - lastEventAt > SSE_IDLE_TIMEOUT_MS) {
        idleTimedOut = true;
        clearInterval(idleTimer);
        controller.abort(new Error("sse idle timeout"));
      }
    }, 5_000);
    let res: Response;
    try {
      try {
        res = await fetch(url, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ locale: getLocale() }),
          signal: controller.signal,
        });
      } catch {
        if (idleTimedOut) {
          throw new ApiError(
            `Request timed out (${SSE_IDLE_TIMEOUT_MS / 1000}s). The live review stream stalled; retry the analysis`,
            0,
            { code: "NET0001", params: { seconds: SSE_IDLE_TIMEOUT_MS / 1000 } },
          );
        }
        if (controller.signal.aborted) {
          throw new ApiError(
            `Request timed out (${Math.round(ANALYZE_TIMEOUT_MS / 1000)}s). Deep review and other LLM tasks can be slow; retry later or check the model/network`,
            0,
            { code: "NET0001", params: { seconds: Math.round(ANALYZE_TIMEOUT_MS / 1000) } },
          );
        }
        throw new ApiError("Cannot reach the backend", 0, { code: "NET0000", params: { url } });
      }
      if (!res.ok) {
        const error = await parseStructuredErrorResponse(res);
        throw new ApiError(error.message, res.status, error);
      }
      let analysis: ResumeAnalysis | null = null;
      const markAlive = () => {
        lastEventAt = Date.now();
      };
      await consumeSSE<ResumeAnalyzeSSEEvent>(
        res,
        (event) => {
          markAlive();
          onEvent?.(event);
        if (event.type === "done" && event.analysis) {
          analysis = event.analysis;
        } else if (event.type === "error") {
          throw new ApiError(event.message || "Deep review failed", 0, {
            code: event.code,
            retryable: event.retryable,
          });
        }
        },
        markAlive,
      );
      if (!analysis) {
        throw new ApiError("Failed to analyze resume: server returned an empty response", res.status, {
          code: "NET0003",
        });
      }
      return analysis;
    } finally {
      clearTimeout(timer);
      clearInterval(idleTimer);
    }
  },
};
