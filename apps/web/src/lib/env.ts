/**
 * Central NEXT_PUBLIC_* reads with load-time validation to avoid:
 *
 * - Scattered duplicate fallback concatenation across files;
 * - Silent localhost fallbacks in production when a required var is missing.
 *
 * Roles (REST actually uses STREAM_API_BASE; see lib/api/apiUrl.ts):
 * - ``NEXT_PUBLIC_API_BASE``: protocol-consistency anchor + error copy; not used directly for REST/SSE;
 * - ``NEXT_PUBLIC_STREAM_API_BASE``: REST and SSE request base;
 * - ``NEXT_PUBLIC_WS_URL``: WebSocket base.
 *
 * Protocol consistency: when ``NEXT_PUBLIC_API_BASE`` is https, ``NEXT_PUBLIC_WS_URL``
 * must be ``wss://``, and vice versa, to avoid mixed-content / downgrade failures.
 */

interface Env {
  /** Protocol check anchor and error copy; REST/SSE use STREAM_API_BASE */
  API_BASE: string;
  WS_BASE: string;
  /** REST and SSE request base (source for apiUrl.ts resolveBackendUrl) */
  STREAM_API_BASE: string;
}

let _cached: Env | null = null;

function readEnv(): Env {
  if (_cached) return _cached;
  const isDev = process.env.NODE_ENV !== "production";

  const apiBase = process.env.NEXT_PUBLIC_API_BASE;
  const wsBase = process.env.NEXT_PUBLIC_WS_URL;
  const streamBase = process.env.NEXT_PUBLIC_STREAM_API_BASE;

  // Production requires explicit values
  if (!isDev) {
    const missing: string[] = [];
    if (!apiBase) missing.push("NEXT_PUBLIC_API_BASE");
    if (!wsBase) missing.push("NEXT_PUBLIC_WS_URL");
    if (!streamBase) missing.push("NEXT_PUBLIC_STREAM_API_BASE");
    if (missing.length > 0) {
      throw new Error(
        `[env] Production requires: ${missing.join(", ")}. See frontend/.env.example`,
      );
    }

    // Protocol consistency: https ↔ wss, http ↔ ws must match.
    const apiIsHttps = apiBase!.startsWith("https://");
    const wsIsSecure = wsBase!.startsWith("wss://");
    const streamIsHttps = streamBase!.startsWith("https://");
    if (apiIsHttps !== wsIsSecure) {
      throw new Error(
        `[env] API_BASE and WS_URL protocol mismatch: api=${apiBase}, ws=${wsBase}`,
      );
    }
    if (apiIsHttps !== streamIsHttps) {
      throw new Error(
        `[env] API_BASE and STREAM_API_BASE protocol mismatch: api=${apiBase}, stream=${streamBase}`,
      );
    }
    // Session cookies are host-scoped: a WS host differing from the REST host
    // silently drops the auth cookie on every handshake (403 reconnect loop).
    const wsHost = new URL(wsBase!).hostname;
    const streamHost = new URL(streamBase!).hostname;
    if (wsHost !== streamHost) {
      throw new Error(
        `[env] WS_URL host must equal STREAM_API_BASE host (cookies are host-scoped): ws=${wsHost}, stream=${streamHost}`,
      );
    }
  }

  const resolvedStreamBase = streamBase || "http://localhost:8081";
  _cached = {
    API_BASE: (apiBase || resolvedStreamBase).replace(/\/+$/, ""),
    // WS must share the REST host: session cookies are host-scoped, so a WS
    // base on a different host (e.g. localhost vs 127.0.0.1) silently drops
    // the auth cookie and every handshake 403s.
    WS_BASE: (wsBase || deriveWsBase(resolvedStreamBase)).replace(/\/+$/, ""),
    STREAM_API_BASE: resolvedStreamBase.replace(/\/+$/, ""),
  };
  return _cached;
}

/** Derive the WS base from the REST base (same host, matching ws/wss scheme). */
function deriveWsBase(streamBase: string): string {
  if (streamBase.startsWith("https://")) return "wss://" + streamBase.slice(8);
  if (streamBase.startsWith("http://")) return "ws://" + streamBase.slice(7);
  return streamBase;
}

/** Return the validated env object. Runs validation on first call. */
export function getEnv(): Env {
  return readEnv();
}
