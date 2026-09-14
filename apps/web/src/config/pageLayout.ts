/**
 * @file pageLayout.ts
 * @description Page layout metadata.
 *
 * AppShell chooses layout shape from this table; add/adjust page layout here so the
 * shell never owns concrete business paths.
 */

/** Full-screen routes (no sidebar; page owns its scroll container), matched by pathname regex. */
export const FULLSCREEN_ROUTE_PATTERNS: readonly RegExp[] = [
  /^\/interview\/\d+/, // interview room
  /^\/resume\/preview/, // resume file preview: standalone page without sidebar
];

/** Fixed-viewport-height routes (sidebar kept; content scrolls inside). */
export const FIXED_HEIGHT_PATHS: readonly string[] = ["/prep", "/interview"];

export function isFullscreenPathname(pathname: string): boolean {
  return FULLSCREEN_ROUTE_PATTERNS.some((pattern) => pattern.test(pathname));
}

export function isFixedHeightPathname(pathname: string): boolean {
  return FIXED_HEIGHT_PATHS.includes(pathname);
}
