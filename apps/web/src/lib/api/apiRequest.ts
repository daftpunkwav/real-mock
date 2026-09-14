/** fetch wrapper: combine timeout signal, credentials, direct backend. */

import { resolveBackendUrl } from "./apiUrl";
import { ApiError, parseStructuredErrorResponse } from "./apiError";

const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;
/** Heavy LLM work: model inference + long JSON often needs 1–3 minutes */
export const LLM_HEAVY_TIMEOUT_MS = 180_000;
/** Resume deep review: Agent tool loop + web search; typically 2–4 minutes, longer when tools run */
export const ANALYZE_TIMEOUT_MS = 480_000;

export async function request<T>(
  path: string,
  options: RequestInit & {
    timeoutMs?: number;
    signal?: AbortSignal;
    /** @deprecated Direct backend is already the default */
    direct?: boolean;
  } = {},
): Promise<T> {
  const {
    timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
    signal: externalSignal,
    direct: _direct = false,
    ...rest
  } = options;
  void _direct; // keep deprecated `direct` in the signature; do not pass to fetch
  // Combine external + timeout signals; abort when either fires.
  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = setTimeout(() => {
    timedOut = true;
    controller.abort(new Error("request timeout"));
  }, timeoutMs);
  const onExternalAbort = () => controller.abort(externalSignal?.reason);
  if (externalSignal) {
    externalSignal.addEventListener("abort", onExternalAbort, { once: true });
    // Re-check after register: sync abort between check and register skips the listener
    if (externalSignal.aborted) {
      externalSignal.removeEventListener("abort", onExternalAbort);
      clearTimeout(timeoutId);
      throw new ApiError("Request cancelled", 0, { code: "NET0002" });
    }
  }
  // Always hit the backend directly so HttpOnly cookies share host with WS
  const url = resolveBackendUrl(`/api${path}`);
  let res: Response;
  try {
    res = await fetch(url, {
      ...rest,
      credentials: "include",
      headers: { "Content-Type": "application/json", ...rest.headers },
      signal: controller.signal,
    });
  } catch {
    if (controller.signal.aborted) {
      if (timedOut) {
        // Localized copy comes from errors catalog (NET0001 + {seconds}); English is catalog-miss fallback
        throw new ApiError(
          timeoutMs > DEFAULT_REQUEST_TIMEOUT_MS
            ? `Request timed out (${Math.round(timeoutMs / 1000)}s). Deep review and other LLM tasks can be slow; retry later or check the model/network`
            : `Request timed out (${Math.round(timeoutMs / 1000)}s). Confirm the backend is running (NEXT_PUBLIC_API_BASE / STREAM_API_BASE)`,
          0,
          { code: "NET0001", params: { seconds: Math.round(timeoutMs / 1000) } },
        );
      }
      throw new ApiError("Request cancelled", 0, { code: "NET0002" });
    }
    throw new ApiError(
      `Cannot reach the backend (${url}). Confirm it is running and NEXT_PUBLIC_STREAM_API_BASE points to the right port`,
      0,
      { code: "NET0000", params: { url } },
    );
  } finally {
    clearTimeout(timeoutId);
    externalSignal?.removeEventListener("abort", onExternalAbort);
  }
  if (!res.ok) {
    const error = await parseStructuredErrorResponse(res);
    throw new ApiError(error.message, res.status, error);
  }
  const text = await res.text();
  if (!text) return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError("Server returned invalid JSON", res.status, { code: "NET0004" });
  }
}
