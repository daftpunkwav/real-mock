"use client";

/** Sidebar navigation content, separated from the responsive shell in Sidebar.tsx. */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { NAV_ITEMS } from "@/config/nav";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { LocaleToggle, useT } from "@/i18n";

/** Match exact routes, descendants, and explicitly declared extra prefixes. */
function isNavActive(
  pathname: string,
  href: string,
  extraActivePrefixes: readonly string[] = [],
): boolean {
  return (
    pathname === href ||
    pathname.startsWith(`${href}/`) ||
    extraActivePrefixes.some(
      (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
    )
  );
}

/** Logo lockup (dot + product name) shared by the desktop toggle and the mobile drawer. */
function BrandText() {
  return (
    <div className="min-w-0 overflow-hidden">
      <h1 className="whitespace-nowrap text-[15px] font-semibold tracking-tight text-[var(--sidebar-foreground)]">
        RealMock
      </h1>
      <p className="whitespace-nowrap text-[10px] uppercase tracking-[0.1em] text-[var(--muted-foreground)]">
        AI Mock Interview
      </p>
    </div>
  );
}

export function NavContent({
  collapsed,
  onNavigate,
  onToggleCollapse,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
  onToggleCollapse?: () => void;
}) {
  const pathname = usePathname();
  const t = useT("nav");
  const tc = useT("common");

  return (
    <>
      {/* Logo doubles as the collapse/expand toggle on desktop; static branding on mobile */}
      <div className="flex h-[60px] items-center border-b border-[var(--sidebar-border)] px-2">
        {onToggleCollapse ? (
          <button
            type="button"
            onClick={onToggleCollapse}
            aria-label={collapsed ? tc("sidebar.expand") : tc("sidebar.collapse")}
            title={collapsed ? tc("sidebar.expand") : tc("sidebar.collapse")}
            className={cn(
              "group flex h-11 w-full items-center gap-2.5 rounded-md px-2 transition-colors duration-base ease-google hover:bg-[var(--sidebar-hover)]",
              collapsed && "justify-center",
            )}
          >
            <span className="g-logo-dot shadow-xs" aria-hidden />
            <AnimatePresence initial={false}>
              {!collapsed && (
                <motion.div
                  className="min-w-0 overflow-hidden"
                  initial={{ opacity: 0, width: 0 }}
                  animate={{ opacity: 1, width: "auto" }}
                  exit={{ opacity: 0, width: 0 }}
                  transition={{ duration: 0.16, ease: [0.2, 0, 0, 1] }}
                >
                  <BrandText />
                </motion.div>
              )}
            </AnimatePresence>
            {!collapsed && (
              <ChevronLeft
                size={15}
                className="ml-auto shrink-0 text-ink-subtle transition-transform duration-base ease-google group-hover:-translate-x-0.5"
              />
            )}
          </button>
        ) : (
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="g-logo-dot shadow-xs" aria-hidden />
            <BrandText />
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav
        className="flex-1 space-y-0.5 overflow-y-auto px-2.5 py-3"
        aria-label={t("aria.main")}
      >
        {NAV_ITEMS.filter((item) => !item.hidden).map((item) => {
          const { href, labelKey, icon: Icon } = item;
          const label = t(labelKey);
          const isActive = isNavActive(pathname, href, item.extraActivePrefixes);
          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              className="block"
              title={collapsed ? label : undefined}
              aria-current={isActive ? "page" : undefined}
            >
              <div
                className={cn(
                  "group/nav relative flex items-center gap-2.5 overflow-hidden rounded-md px-2.5 py-2 text-[13px] transition-colors duration-base ease-google",
                  isActive
                    ? "bg-[var(--sidebar-active)] font-medium text-[var(--sidebar-accent-foreground)]"
                    : "text-[var(--sidebar-foreground)] hover:bg-[var(--sidebar-hover)]",
                )}
              >
                {/* Active-route indicator */}
                {isActive && (
                  <span
                    className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-[var(--sidebar-primary)]"
                    aria-hidden
                  />
                )}
                <Icon
                  size={17}
                  strokeWidth={isActive ? 2 : 1.75}
                  className={cn(
                    "shrink-0 transition-all duration-base ease-google group-hover/nav:scale-110",
                    isActive
                      ? "text-[var(--sidebar-primary)]"
                      : "text-[var(--muted-foreground)] group-hover/nav:text-[var(--sidebar-foreground)]",
                  )}
                />
                {/* Label stays mounted through the width animation; only opacity toggles. */}
                <span
                  className={cn(
                    "min-w-0 flex-1 truncate transition-opacity duration-base ease-google",
                    collapsed && "opacity-0",
                  )}
                >
                  {label}
                </span>
                <ChevronRight
                  size={13}
                  className={cn(
                    "shrink-0 -translate-x-1 text-ink-subtle opacity-0 transition-all duration-base ease-google",
                    !collapsed && "group-hover/nav:translate-x-0 group-hover/nav:opacity-100",
                    isActive && !collapsed && "translate-x-0 text-[var(--sidebar-primary)] opacity-60",
                  )}
                />
              </div>
            </Link>
          );
        })}
      </nav>

      {/* Locale and theme controls: side-by-side when expanded, stacked icons when collapsed */}
      <div
        className={cn(
          "border-t border-[var(--sidebar-border)]",
          collapsed ? "px-1 pt-2" : "grid grid-cols-2 gap-1 px-3 pb-2 pt-2",
        )}
      >
        <LocaleToggle collapsed={collapsed} />
        <ThemeToggle collapsed={collapsed} />
      </div>
    </>
  );
}
