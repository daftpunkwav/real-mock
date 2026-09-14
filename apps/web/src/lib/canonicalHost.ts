/**
 * @file canonicalHost.ts
 * @description Pre-hydration script: pin the loopback host to 127.0.0.1.
 *
 * Session capability cookies (and localStorage) are host-bound, so alternating
 * between localhost and 127.0.0.1 silently orphans sessions (visible in lists,
 * 401 on every action). A server-side redirect cannot implement this pinning
 * (transparent proxies relativize cross-loopback Location headers into
 * self-loops), so the client navigates itself once, before first paint.
 */

/** Redirect localhost/[::1] pages to the canonical 127.0.0.1 origin. */
export const canonicalHostInitScript = `(() => {
  try {
    var h = window.location.hostname.toLowerCase();
    if (h === "localhost" || h === "[::1]" || h === "::1") {
      var port = window.location.port ? ":" + window.location.port : "";
      window.location.replace(
        "http://127.0.0.1" + port + window.location.pathname +
        window.location.search + window.location.hash
      );
    }
  } catch (_) {}
})();`;
