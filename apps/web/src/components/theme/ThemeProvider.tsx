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

type ThemeContextValue = {
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;
};

const STORAGE_KEY = "realmock-theme";
const ThemeContext = createContext<ThemeContextValue | null>(null);

function getSystemTheme(): "light" | "dark" {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyThemeClass(resolved: ThemeMode) {
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
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

  const setTheme = useCallback((next: ThemeMode) => {
    targetRef.current = next;
    setThemeState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
    applyThemeClass(next);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(targetRef.current === "dark" ? "light" : "dark");
  }, [setTheme]);

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
