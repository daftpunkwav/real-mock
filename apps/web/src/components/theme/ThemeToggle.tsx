"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "./ThemeProvider";
import { useT } from "@/i18n";

/** Sidebar theme switch: toggles light/dark with a plain, instant swap. */
export function ThemeToggle({ collapsed = false }: { collapsed?: boolean }) {
  const { theme, toggleTheme } = useTheme();
  const t = useT("common");
  const nextLabel = t(theme === "dark" ? "theme.light" : "theme.dark");

  const Icon = theme === "dark" ? Moon : Sun;
  const label = t(theme === "dark" ? "theme.dark" : "theme.light");

  return (
    <button
      type="button"
      onClick={toggleTheme}
      title={t("theme.toggle.title", { label: nextLabel })}
      aria-label={t("theme.toggle.aria", { label: nextLabel })}
      className={
        collapsed
          ? "mx-auto mb-3 flex h-9 w-9 items-center justify-center rounded-md text-ink-muted hover:bg-surface-muted hover:text-ink"
          : "flex h-9 w-full items-center justify-center gap-1.5 rounded-md text-[13px] text-ink-muted transition-colors duration-base ease-google hover:bg-surface-muted hover:text-ink"
      }
    >
      {/* Sun/Moon are different component types, so the icon remounts on
          each flip — the mount animation doubles as the state-change cue. */}
      <Icon size={16} className="theme-icon-swap shrink-0" />
      {!collapsed && <span className="truncate">{label}</span>}
    </button>
  );
}
