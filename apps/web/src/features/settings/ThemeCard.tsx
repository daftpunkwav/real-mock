"use client";

/** Theme switcher card for the settings page (light / dark). */

import { Moon, Sun, type LucideIcon } from "lucide-react";
import type { MouseEvent } from "react";
import { useTheme, type ThemeMode } from "@/components/theme/ThemeProvider";
import { useT } from "@/i18n";

const THEME_OPTIONS: { mode: ThemeMode; labelKey: string; icon: LucideIcon }[] = [
  { mode: "light", labelKey: "theme.light", icon: Sun },
  { mode: "dark", labelKey: "theme.dark", icon: Moon },
];

export function ThemeCard() {
  const { theme, setTheme } = useTheme();
  const t = useT("settings");
  const tc = useT("common");

  const pick = (mode: ThemeMode) => (e: MouseEvent<HTMLButtonElement>) => {
    // Spread from the exact cursor point; keyboard activation (detail 0) gets
    // an instant, animation-free switch.
    setTheme(mode, e.detail === 0 ? undefined : { x: e.clientX, y: e.clientY });
  };

  return (
    <div className="surface-card p-4">
      <div className="mb-1 flex items-center gap-2">
        <Sun size={16} className="text-ink-muted" />
        <h2 className="text-[14px] font-semibold">{t("theme.title")}</h2>
      </div>
      <div className="segmented mt-2 max-w-xs">
        {THEME_OPTIONS.map(({ mode, labelKey, icon: Icon }) => (
          <button
            key={mode}
            type="button"
            onClick={pick(mode)}
            data-active={theme === mode}
            aria-pressed={theme === mode}
            className="segmented-item flex-1 !h-7 !text-xs"
          >
            <Icon size={12} />
            <span>{tc(labelKey)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
