"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "./ThemeProvider";
import { useT } from "@/i18n";

const LABEL_KEYS = {
  light: "theme.light",
  dark: "theme.dark",
  system: "theme.system",
} as const;

/** Sidebar theme switch: one button that cycles light → dark → system. */
export function ThemeToggle({ collapsed = false }: { collapsed?: boolean }) {
  const { theme, cycleTheme } = useTheme();
  const t = useT("common");
  const label = t(LABEL_KEYS[theme]);
  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;

  return (
    <button
      type="button"
      onClick={cycleTheme}
      title={t("theme.toggle.title", { label })}
      aria-label={t("theme.toggle.aria", { label })}
      className={
        collapsed
          ? "mx-auto mb-3 flex h-9 w-9 items-center justify-center rounded-md text-ink-muted hover:bg-surface-muted hover:text-ink"
          : "flex h-9 w-full items-center justify-center gap-1.5 rounded-md text-[13px] text-ink-muted transition-colors duration-base ease-google hover:bg-surface-muted hover:text-ink"
      }
    >
      <Icon size={16} className="shrink-0" />
      {!collapsed && <span className="truncate">{label}</span>}
    </button>
  );
}
