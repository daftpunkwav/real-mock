/** API error normalization and predicates: ApiError / abort detection / formatting / FastAPI response parsing. */

// Import i18n via deep paths, not the @/i18n barrel: the barrel pulls in .tsx
// (LocaleProvider/Toggle) and vitest cannot transform those modules.
import { localizeApiError } from "@/i18n/errors";
import { getTranslator } from "@/i18n/resolve";

export interface ApiErrorOptions {
  code?: string;
  hint?: string;
  traceId?: string;
  retryable?: boolean;
  /** Interpolation params for {name} placeholders in the i18n errors catalog */
  params?: Record<string, string | number>;
}

export class ApiError extends Error {
  status: number;
  code: string;
  hint: string;
  traceId: string;
  retryable: boolean;
  params?: Record<string, string | number>;

  constructor(message: string, status: number, options: ApiErrorOptions = {}) {
    super(message);
    this.status = status;
    this.code = options.code ?? (status === 0 ? "NET0000" : `http_${status}`);
    this.hint = options.hint ?? "";
    this.traceId = options.traceId ?? "";
    this.retryable = options.retryable ?? false;
    this.params = options.params;
    this.name = "ApiError";
  }
}

/**
 * Single exit: when ``code`` hits the i18n errors catalog, emit localized copy;
 * otherwise fall back to the server message (see i18n/errors.ts). Non-ApiError values pass through.
 */
export function formatApiError(error: unknown): string {
  return localizeApiError(error);
}

/** True when the request was aborted (unload, retry, or a superseded load). */
export function isRequestAborted(error: unknown): boolean {
  return error instanceof ApiError && error.code === "NET0002";
}

export interface ParsedApiError extends ApiErrorOptions {
  message: string;
}

export async function parseStructuredErrorResponse(res: Response): Promise<ParsedApiError> {
  const text = await res.text();
  if (!text) return { message: getTranslator("common")("request.failed", { status: res.status }) };
  try {
    const data = JSON.parse(text) as {
      detail?: unknown;
      message?: string;
      error?: {
        code?: string;
        message?: string;
        hint?: string;
        trace_id?: string;
        retryable?: boolean;
        params?: Record<string, string | number>;
      };
    };
    if (data.error?.message) {
      return {
        message: data.error.message,
        code: data.error.code,
        hint: data.error.hint,
        traceId: data.error.trace_id,
        retryable: data.error.retryable,
        params: data.error.params,
      };
    }
    if (typeof data.detail === "string") return { message: data.detail };
    if (Array.isArray(data.detail)) {
      return {
        message: data.detail
          .map((item) =>
            typeof item === "object" && item && "msg" in item
              ? String((item as { msg: string }).msg)
              : String(item),
          )
          .join("; "),
      };
    }
    if (data.detail) return { message: JSON.stringify(data.detail) };
    if (data.message) return { message: data.message };
  } catch {
    // Non-JSON body: fall through to raw-text fallback.
  }
  return { message: text.length > 300 ? `${text.slice(0, 300)}…` : text };
}
