"use client";

/**
 * @file useAlignedBackendUrl.ts
 * @description Hydration-safe backend URL: first render matches SSR, loopback host aligns after mount.
 */

import { useEffect, useState } from "react";
import { resolveBackendUrl, resolveServerBackendUrl } from "./apiUrl";

/**
 * Return a backend URL for rendered ``href`` / ``src`` attributes.
 *
 * The initial value equals ``resolveServerBackendUrl`` (what SSR emitted),
 * so hydration never mismatches when the page host differs from
 * ``STREAM_API_BASE`` (localhost vs 127.0.0.1). After mount, an effect
 * swaps in the loopback-aligned URL for CORS / PNA parity.
 */
export function useAlignedBackendUrl(apiPath: string): string {
  const [url, setUrl] = useState(() => resolveServerBackendUrl(apiPath));
  useEffect(() => {
    setUrl(resolveBackendUrl(apiPath));
  }, [apiPath]);
  return url;
}
