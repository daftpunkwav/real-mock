/**
 * @file nav.ts
 * @description Frontend route / navigation config.
 *
 * Keep every menu item here so adding/removing pages is a single edit.
 *
 * - ``icon`` must be a ``lucide-react`` icon component;
 * - ``hidden`` temporarily hides an item (e.g. not shipped yet).
 */
import {
  Home,
  User,
  FileText,
  Settings,
  Mic,
  BarChart3,
  TrendingUp,
  BookOpen,
  type LucideIcon,
} from "lucide-react";
import type { MessageKey } from "@/i18n";

export interface NavItem {
  href: string;
  /**
   * Menu copy message key (i18n nav namespace, e.g. "items.home").
   * Visible strings live in src/i18n/messages/; this file keeps structure and icons only.
   */
  labelKey: MessageKey<"nav">;
  icon: LucideIcon;
  hidden?: boolean;
  /**
   * Extra active prefixes (route segments) when another route should highlight this item,
   * e.g. report detail `/report/[id]` under History. The shell should not hard-code business paths.
   */
  extraActivePrefixes?: readonly string[];
}

export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/", labelKey: "items.home", icon: Home },
  { href: "/profile", labelKey: "items.profile", icon: User },
  { href: "/resume", labelKey: "items.resume", icon: FileText },
  { href: "/prep", labelKey: "items.prep", icon: BookOpen },
  { href: "/interview", labelKey: "items.interview", icon: Mic },
  { href: "/history", labelKey: "items.history", icon: BarChart3, extraActivePrefixes: ["/report"] },
  { href: "/growth", labelKey: "items.growth", icon: TrendingUp },
  { href: "/settings", labelKey: "items.settings", icon: Settings },
] as const;
