"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

export type ThemeMode = "light" | "dark";

/** Viewport point the theme transition spreads from (usually the mouse). */
export type ThemeOrigin = { x: number; y: number };

type ThemeContextValue = {
  theme: ThemeMode;
  setTheme: (theme: ThemeMode, origin?: ThemeOrigin) => void;
  toggleTheme: (origin?: ThemeOrigin) => void;
};

const STORAGE_KEY = "realmock-theme";
const ThemeContext = createContext<ThemeContextValue | null>(null);

function getSystemTheme(): "light" | "dark" {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function applyThemeClass(resolved: ThemeMode) {
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
}

/** Rhythm differs per direction: lights-off rolls in deliberately, lights-on
 * floods. The reveal is always faster than the cover (exit faster than enter). */
const VEIL_TIMING: Record<ThemeMode, { in: number; out: number; swapAt: number }> = {
  dark: { in: 400, out: 300, swapAt: 0.85 },
  light: { in: 260, out: 240, swapAt: 0.9 },
};
/* The dissolve uses the app's own token curve for cohesion; the reveal gets a
   punchier ease-out. Never ease-in — it delays the moment the eye is watching. */
const EASE_DISSOLVE = "cubic-bezier(0.2, 0, 0, 1)";
const EASE_REVEAL = "cubic-bezier(0.23, 1, 0.32, 1)";

/**
 * Resolve the target theme's background without hard-coding tokens. Custom
 * properties inherit, so a probe inside `html.dark` would still read dark
 * values; and body's background-color *transitions*, so reading that property
 * right after the class flip yields the old color. Flip the root class
 * synchronously and read the `--background` custom property instead — it
 * resolves instantly and never transitions. Same-frame reads never paint.
 */
function targetBackground(resolved: ThemeMode): string {
  const root = document.documentElement;
  const wasDark = root.classList.contains("dark");
  root.classList.toggle("dark", resolved === "dark");
  const bg = getComputedStyle(document.body).getPropertyValue("--background").trim();
  root.classList.toggle("dark", wasDark);
  return bg || (resolved === "dark" ? "#161616" : "#ffffff");
}

interface Veil {
  el: HTMLDivElement;
  target: ThemeMode;
  /** "in" = dissolving toward the target (swap pending); "out" = revealing it. */
  phase: "in" | "out";
  timer?: ReturnType<typeof setTimeout>;
}

let veil: Veil | null = null;

function clearVeil() {
  if (!veil) return;
  clearTimeout(veil.timer);
  veil.el.remove();
  veil = null;
}

/**
 * Lights-off / lights-on: the whole page dissolves into the target background
 * through a soft veil whose radial weight sits on the mouse point — nearby
 * pixels lead, the corners trail, so the change visibly "spreads" from the
 * click. The theme flips while the veil is at peak opacity (invisible), then
 * the veil fades out revealing the new theme (渐变 → 换轨 → 渐灭). Opacity-only
 * animation: compositor work, no repaints, and no dead time where the page
 * sits frozen before an instant swap.
 */
function spreadTheme(resolved: ThemeMode, origin?: ThemeOrigin) {
  // Keyboard-initiated toggles get no spread (no mouse point to spread from,
  // and the action must feel instant).
  if (!origin) {
    clearVeil();
    applyThemeClass(resolved);
    return;
  }
  if (prefersReducedMotion()) {
    // Reduced motion keeps a gentle comprehension cue: instant swap plus a
    // short opacity-only veil of the target color (no movement).
    clearVeil();
    applyThemeClass(resolved);
    const el = document.createElement("div");
    el.className = "theme-spread-overlay";
    el.style.background = targetBackground(resolved);
    el.style.opacity = "1";
    document.body.appendChild(el);
    el.animate([{ opacity: 1 }, { opacity: 0 }], {
      duration: 150,
      easing: EASE_REVEAL,
    }).onfinish = () => el.remove();
    setTimeout(() => el.remove(), 250);
    return;
  }
  // Already dissolving toward that theme: nothing to do.
  if (veil && veil.target === resolved) return;

  if (veil && veil.phase === "in") {
    // Toggled back mid-dissolve: the applied theme already equals `resolved`,
    // so melt the veil away instead of completing the old transition.
    const dying = veil;
    veil = null;
    clearTimeout(dying.timer);
    applyThemeClass(resolved);
    const current = getComputedStyle(dying.el).opacity;
    dying.el
      .animate([{ opacity: current }, { opacity: 0 }], {
        duration: 180,
        easing: EASE_DISSOLVE,
        fill: "forwards",
      })
      .onfinish = () => dying.el.remove();
    // Animation events freeze in background tabs; guarantee cleanup anyway.
    setTimeout(() => dying.el.remove(), 280);
    return;
  }
  // A veil in its fade-out phase already swapped; melt it faster and grow the
  // new one on top.
  if (veil) {
    const dying = veil;
    veil = null;
    clearTimeout(dying.timer);
    const current = getComputedStyle(dying.el).opacity;
    dying.el
      .animate([{ opacity: current }, { opacity: 0 }], {
        duration: 180,
        easing: EASE_DISSOLVE,
        fill: "forwards",
      })
      .onfinish = () => dying.el.remove();
    setTimeout(() => dying.el.remove(), 280);
  }

  const bg = targetBackground(resolved);
  const timing = VEIL_TIMING[resolved];
  // Distance to the farthest viewport corner: the gradient stays opaque well
  // past it, so at peak opacity every pixel is covered when the theme flips.
  const farthest = Math.hypot(
    Math.max(origin.x, window.innerWidth - origin.x),
    Math.max(origin.y, window.innerHeight - origin.y),
  );
  const el = document.createElement("div");
  el.className = "theme-spread-overlay";
  el.style.background = `radial-gradient(circle at ${origin.x}px ${origin.y}px, ${bg} 0%, ${bg} ${Math.round(farthest * 0.55)}px, color-mix(in srgb, ${bg} 86%, transparent) ${Math.round(farthest * 1.02)}px)`;
  el.style.opacity = "0";
  document.body.appendChild(el);

  const entry: Veil = { el, target: resolved, phase: "in" };
  veil = entry;

  const settle = () => {
    if (veil !== entry || entry.phase === "out") return;
    entry.phase = "out";
    clearTimeout(entry.timer);
    applyThemeClass(resolved);
    const fade = el.animate([{ opacity: 1 }, { opacity: 0 }], {
      duration: timing.out,
      easing: EASE_REVEAL,
      fill: "forwards",
    });
    fade.onfinish = () => {
      el.remove();
      if (veil === entry) veil = null;
    };
    // Animation events freeze in background tabs; guarantee the cleanup.
    setTimeout(() => {
      el.remove();
      if (veil === entry) veil = null;
    }, timing.out + 120);
  };

  el.animate([{ opacity: 0 }, { opacity: 1 }], {
    duration: timing.in,
    easing: EASE_DISSOLVE,
    fill: "forwards",
  }).onfinish = settle;
  // Timer fallback: the swap must not depend solely on animation events.
  entry.timer = setTimeout(settle, timing.in * timing.swapAt + 40);
}

function readStoredTheme(): ThemeMode {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === "light" || raw === "dark") return raw;
    // Legacy values ("system") migrate to an explicit choice on first load.
    const resolved: ThemeMode = getSystemTheme();
    localStorage.setItem(STORAGE_KEY, resolved);
    return resolved;
  } catch {
    return "light";
  }
}

/** Apply the stored theme before hydration to prevent a first-paint flash. */
export const themeInitScript = `(() => {
  try {
    const key = ${JSON.stringify(STORAGE_KEY)};
    const stored = localStorage.getItem(key);
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    let theme = stored === "light" || stored === "dark" ? stored : (prefersDark ? "dark" : "light");
    if (stored !== theme) localStorage.setItem(key, theme);
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.style.colorScheme = theme;
  } catch (_) {}
})();`;

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemeMode>("light");
  // Synchronous mirror of the requested target: rapid toggles must alternate
  // correctly even before React re-renders.
  const targetRef = useRef<ThemeMode>("light");

  useEffect(() => {
    const stored = readStoredTheme();
    targetRef.current = stored;
    setThemeState(stored);
    applyThemeClass(stored);
  }, []);

  const setTheme = useCallback((next: ThemeMode, origin?: ThemeOrigin) => {
    targetRef.current = next;
    setThemeState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
    spreadTheme(next, origin);
  }, []);

  const toggleTheme = useCallback(
    (origin?: ThemeOrigin) => {
      setTheme(targetRef.current === "dark" ? "light" : "dark", origin);
    },
    [setTheme],
  );

  const value = useMemo(
    () => ({ theme, setTheme, toggleTheme }),
    [theme, setTheme, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return ctx;
}
