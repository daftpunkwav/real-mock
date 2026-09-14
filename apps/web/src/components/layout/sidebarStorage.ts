/** Sidebar shell persistence: a cookie so the server can SSR the right state.
 *
 * Server rendering cannot read localStorage, so collapse/width live in a
 * cookie (mirroring the locale pattern): RootLayout reads it per request and
 * passes the initial state down through AppShell, giving a correct first
 * paint with no expand-then-collapse flash. Client writes keep it in sync.
 */

export const SIDEBAR_COOKIE_KEY = "realmock.sidebar";
const SIDEBAR_COOKIE_MAX_AGE = 31536000; // 1 year

export const SIDEBAR_DEFAULT_WIDTH = 248;
export const SIDEBAR_MIN_WIDTH = 200;
export const SIDEBAR_MAX_WIDTH = 360;

export interface SidebarPersistedState {
  collapsed: boolean;
  width: number;
}

export function defaultSidebarState(): SidebarPersistedState {
  return { collapsed: false, width: SIDEBAR_DEFAULT_WIDTH };
}

function clampWidth(value: unknown): number {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return SIDEBAR_DEFAULT_WIDTH;
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, n));
}

/** Parse a stored value (cookie or otherwise); falls back to defaults. */
export function parseSidebarState(raw: string | null | undefined): SidebarPersistedState {
  if (!raw) return defaultSidebarState();
  const candidates = [raw];
  try {
    const decoded = decodeURIComponent(raw);
    if (decoded !== raw) candidates.unshift(decoded);
  } catch {
    /* keep raw */
  }
  for (const text of candidates) {
    try {
      const data = JSON.parse(text) as Partial<SidebarPersistedState>;
      return {
        collapsed: data.collapsed === true,
        width: clampWidth(data.width),
      };
    } catch {
      /* try next */
    }
  }
  return defaultSidebarState();
}

/** Client-side write; silently ignored where cookies are blocked. */
export function writeSidebarState(state: SidebarPersistedState): void {
  try {
    document.cookie = `${SIDEBAR_COOKIE_KEY}=${encodeURIComponent(
      JSON.stringify(state),
    )}; path=/; max-age=${SIDEBAR_COOKIE_MAX_AGE}; samesite=lax`;
  } catch {
    /* ignore */
  }
}
