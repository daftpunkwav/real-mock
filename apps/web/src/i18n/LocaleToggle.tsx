"use client";

/** Shell locale switch (mirrors ThemeToggle): one cycle button for both widths. */

import { Languages } from "lucide-react";
import { LOCALE_META } from "./locales";
import { useLocale, useT } from "./localeContext";

export function LocaleToggle({ collapsed = false }: { collapsed?: boolean }) {
  const { locale, setLocale, locales } = useLocale();
  const t = useT("common");

  const idx = locales.indexOf(locale);
  const next = locales[(idx + 1) % locales.length] ?? locale;
  const label = LOCALE_META[locale].nativeLabel;

  return (
    <button
      type="button"
      onClick={() => setLocale(next)}
      title={t("locale.toggle.title", { label })}
      aria-label={t("locale.toggle.aria", { label })}
      className={
        collapsed
          ? "mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-md text-[11px] font-medium text-ink-muted hover:bg-surface-muted hover:text-ink"
          : "flex h-9 w-full items-center justify-center gap-1.5 rounded-md text-[13px] text-ink-muted transition-colors duration-base ease-google hover:bg-surface-muted hover:text-ink"
      }
    >
      {collapsed ? (
        <span>{LOCALE_META[locale].shortLabel}</span>
      ) : (
        <>
          <Languages size={16} className="shrink-0" />
          <span className="truncate">{label}</span>
        </>
      )}
    </button>
  );
}
