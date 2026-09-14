"use client";

/**
 * Settings shell: two-column layout — category rail on the left, active
 * panel on the right. Categories come from the settings registry.
 */

import { useState } from "react";
import {
  DEFAULT_CATEGORY_ID,
  getSettingsCategory,
  SETTINGS_CATEGORIES,
  type SettingsCategoryId,
} from "@/features/settings/registry";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

export default function SettingsPage() {
  const t = useT("settings");
  const [categoryId, setCategoryId] = useState<SettingsCategoryId>(DEFAULT_CATEGORY_ID);
  const { id: activeId, Panel: ActivePanel } = getSettingsCategory(categoryId);

  return (
    <div className="page-shell anim-rise">
      <div className="page-header !mb-4">
        <h1 className="page-title">{t("page.title")}</h1>
      </div>

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[200px_1fr]">
        {/* Category rail */}
        <nav className="surface-card p-1.5" aria-label={t("page.title")}>
          {SETTINGS_CATEGORIES.map(({ id, labelKey, icon: Icon }) => {
            const selected = id === activeId;
            return (
              <button
                key={id}
                type="button"
                onClick={() => setCategoryId(id)}
                aria-current={selected ? "true" : undefined}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] transition-colors duration-base ease-google",
                  selected
                    ? "bg-surface-muted font-medium text-ink"
                    : "text-ink-muted hover:bg-surface-muted hover:text-ink",
                )}
              >
                <Icon size={16} className="shrink-0" />
                <span className="truncate">{t(labelKey)}</span>
              </button>
            );
          })}
        </nav>

        {/* Active category detail */}
        <div className="min-w-0">
          <ActivePanel />
        </div>
      </div>
    </div>
  );
}
