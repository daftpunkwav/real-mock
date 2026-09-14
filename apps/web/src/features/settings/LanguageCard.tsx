"use client";

/** Interface language switcher card for the settings page. */

import { Languages } from "lucide-react";
import { LOCALE_META, useLocale, useT } from "@/i18n";

export function LanguageCard() {
  const { locale, setLocale, locales } = useLocale();
  const t = useT("settings");

  return (
    <div className="surface-card p-4">
      <div className="mb-1 flex items-center gap-2">
        <Languages size={16} className="text-ink-muted" />
        <h2 className="text-[14px] font-semibold">{t("language.title")}</h2>
      </div>
      <div className="segmented mt-2 max-w-xs">
        {locales.map((id) => (
          <button
            key={id}
            type="button"
            onClick={() => setLocale(id)}
            data-active={locale === id}
            aria-pressed={locale === id}
            className="segmented-item flex-1"
          >
            {LOCALE_META[id].nativeLabel}
          </button>
        ))}
      </div>
      <p className="mt-2 text-xs text-ink-muted">{t("language.hint")}</p>
    </div>
  );
}
