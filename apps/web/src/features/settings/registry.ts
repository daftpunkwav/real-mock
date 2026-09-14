/** Settings category registry: the shell renders whatever is listed here. */

import type { ComponentType } from "react";
import type { LucideIcon } from "lucide-react";
import { Cpu, Database, GraduationCap, Palette, PlugZap } from "lucide-react";
import { IntegrationsSettingsPanel } from "./IntegrationsSettingsPanel";
import { InterfaceSettingsPanel } from "./InterfaceSettingsPanel";
import { ModelsSettingsPanel } from "./ModelsSettingsPanel";
import { PrepSettingsPanel } from "./PrepSettingsPanel";
import { ResumeSettingsPanel } from "./ResumeSettingsPanel";

/** Categories group settings by domain: global, resumes, interview prep. */
export type SettingsCategoryId = "interface" | "models" | "resume" | "prep" | "integrations";

export type SettingsCategory = {
  id: SettingsCategoryId;
  /** i18n key in the settings namespace */
  labelKey: string;
  icon: LucideIcon;
  Panel: ComponentType;
};

/** Add a new category by appending an entry; no shell changes needed. */
export const SETTINGS_CATEGORIES = [
  { id: "interface", labelKey: "nav.interface", icon: Palette, Panel: InterfaceSettingsPanel },
  { id: "models", labelKey: "nav.models", icon: Cpu, Panel: ModelsSettingsPanel },
  { id: "resume", labelKey: "nav.resume", icon: Database, Panel: ResumeSettingsPanel },
  { id: "prep", labelKey: "nav.prep", icon: GraduationCap, Panel: PrepSettingsPanel },
  { id: "integrations", labelKey: "nav.integrations", icon: PlugZap, Panel: IntegrationsSettingsPanel },
] as const satisfies readonly [SettingsCategory, ...SettingsCategory[]];

/** First listed category is the default; derive it so order and ids stay in sync. */
export const DEFAULT_CATEGORY_ID: SettingsCategoryId = SETTINGS_CATEGORIES[0].id;

export function getSettingsCategory(id: SettingsCategoryId): SettingsCategory {
  return SETTINGS_CATEGORIES.find((c) => c.id === id) ?? SETTINGS_CATEGORIES[0];
}
