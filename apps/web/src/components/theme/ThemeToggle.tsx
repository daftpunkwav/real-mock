"use client";

import { Moon, Sun } from "lucide-react";
import type { MouseEvent } from "react";
import { useTheme } from "./ThemeProvider";
import { useT } from "@/i18n";

/** Sidebar theme switch: toggles light/dark, spreading from the click point. */
export function ThemeToggle({ collapsed = false }: { collapsed?: boolean }) {
  const { theme, toggleTheme } = useTheme();
  const t = useT("common");
  const nextLabel = t(theme === "dark" ? "theme.light" : "theme.dark");

  const onClick = (e: MouseEvent<HTMLButtonElement>) => {
    // Spread from the exact cursor point; keyboard activation (detail 0) gets
    // an instant, animation-free switch.
    toggleTheme(e.detail === 0 ? undefined : { x: e.clientX, y: e.clientY });
  };

  const Icon = theme === "dark" ? Moon : Sun;
  const label = t(theme === "dark" ? "theme.dark" : "theme.light");

  return (
    <button
      type="button"
      onClick={onClick}
      title={t("theme.toggle.title", { label: nextLabel })}
      aria-label={t("theme.toggle.aria", { label: nextLabel })}
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
