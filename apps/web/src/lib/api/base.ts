/** API client base layer (aggregated re-exports)
 *
 * fetch wrapper / SSE parsing / error normalization / URL resolution.
 * Capability clients (settings/profile/resume/prep/interview/report/growth) share this layer.
 * Implementations live in apiUrl / apiError / apiRequest / apiSse.
 *
 * All calls hit the backend directly (``NEXT_PUBLIC_API_BASE`` / ``STREAM_API_BASE``)
 * with ``credentials: "include"`` for HttpOnly cookies. Error parsing accepts FastAPI
 * ``{detail: ...}`` and the unified ``{error:{code,message,trace_id}}`` envelope.
 */

export { resolveBackendUrl, resolveServerBackendUrl } from "./apiUrl";
export {
  ApiError,
  formatApiError,
  isRequestAborted,
  parseStructuredErrorResponse,
  type ApiErrorOptions,
  type ParsedApiError,
} from "./apiError";
export { LLM_HEAVY_TIMEOUT_MS, ANALYZE_TIMEOUT_MS, request } from "./apiRequest";
export { consumeSSE } from "./apiSse";
