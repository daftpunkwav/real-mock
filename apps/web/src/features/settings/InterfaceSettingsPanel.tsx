"use client";

/** Interface category: appearance preferences (theme, language). */

import { LanguageCard } from "./LanguageCard";
import { ThemeCard } from "./ThemeCard";

export function InterfaceSettingsPanel() {
  return (
    <div className="space-y-4">
      <ThemeCard />
      <LanguageCard />
    </div>
  );
}
