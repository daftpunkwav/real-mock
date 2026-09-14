/** Direct-backend URL resolution with loopback hostname alignment (localhost ↔ 127.0.0.1). */

import { getEnv } from "@/lib/env";

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);

/**
 * Resolve the final backend URL (cookies share host with WS).
 *
 * On loopback, align STREAM_API_BASE hostname to the page hostname
 * (localhost ↔ 127.0.0.1) to reduce CORS / PNA failures.
 *
 * Hydration rule: values rendered into SSR HTML (``href`` / ``src``) must use
 * ``resolveServerBackendUrl`` (or ``useAlignedBackendUrl``) so the first
 * client render matches the server. ``resolveBackendUrl`` reads
 * ``window.location`` and must only run in effects / event handlers for
 * rendered attributes.
 */
export function resolveServerBackendUrl(apiPath: string): string {
  const path = apiPath.startsWith("/") ? apiPath : `/${apiPath}`;
  return `${getEnv().STREAM_API_BASE}${path}`;
}

/**
 * Align a base URL's loopback hostname to the page hostname (localhost ↔
 * 127.0.0.1). Session cookies are host-scoped, so REST and WS must resolve to
 * the exact host the cookie was issued for — a mismatch silently drops the
 * auth cookie and every request 403s. Returns the base unchanged off-loopback.
 */
function alignLoopbackBase(base: string): string {
  if (typeof window === "undefined") return base;
  try {
    const u = new URL(base);
    const pageHost = window.location.hostname.toLowerCase();
    if (LOOPBACK_HOSTS.has(u.hostname) && LOOPBACK_HOSTS.has(pageHost)) {
      u.hostname = pageHost === "[::1]" || pageHost === "::1" ? "localhost" : pageHost;
    }
    return u.origin;
  } catch {
    return base;
  }
}

/** Resolve the final WebSocket URL (loopback-aligned; same host as REST). */
export function resolveBackendWsUrl(wsPath: string): string {
  const path = wsPath.startsWith("/") ? wsPath : `/${wsPath}`;
  return `${alignLoopbackBase(getEnv().WS_BASE)}${path}`;
}

export function resolveBackendUrl(apiPath: string): string {
  const path = apiPath.startsWith("/") ? apiPath : `/${apiPath}`;
  return `${alignLoopbackBase(getEnv().STREAM_API_BASE)}${path}`;
}
