"use client";

/** Sidebar navigation content, separated from the responsive shell in Sidebar.tsx. */

import Link, { useLinkStatus } from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, PanelLeftClose } from "lucide-react";
import { NAV_ITEMS } from "@/config/nav";
import { cn } from "@/lib/utils";
import { LogoMark } from "@/components/brand/LogoMark";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { useT } from "@/i18n";

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

/** Wordmark lockup (mark + name) shared by the expanded header and the mobile drawer. */
function BrandLockup({ markSize = 26 }: { markSize?: number }) {
  return (
    <>
      <LogoMark size={markSize} />
      <div className="min-w-0 flex-1 overflow-hidden">
        <h1 className="whitespace-nowrap text-[15px] font-semibold tracking-tight text-[var(--sidebar-foreground)]">
          Real Mock
        </h1>
        <p className="whitespace-nowrap text-[10px] uppercase tracking-[0.1em] text-[var(--muted-foreground)]">
          AI Mock Interview
        </p>
      </div>
    </>
  );
}

/**
 * In-flight indicator for the Link it renders in: stays visible from click until
 * the target route actually renders, so slow navigations (first compile in dev,
 * chunk load) never feel like a dead click.
 */
function NavPendingBar() {
  const { pending } = useLinkStatus();
  if (!pending) return null;
  return <span className="nav-pending-bar" aria-hidden />;
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
      {/* Brand header: expanded shows the wordmark plus a round collapse control;
          collapsed turns the mark itself into the expand control (mobile: static). */}
      <div className="flex h-[60px] shrink-0 items-center gap-2.5 border-b border-[var(--sidebar-border)] px-3">
        {onToggleCollapse && collapsed ? (
          <button
            type="button"
            onClick={onToggleCollapse}
            aria-label={tc("sidebar.expand")}
            title={tc("sidebar.expand")}
            className="mx-auto flex h-9 w-9 items-center justify-center rounded-full transition-colors duration-base ease-google hover:bg-[var(--sidebar-hover)]"
          >
            <LogoMark size={24} />
          </button>
        ) : (
          <>
            <BrandLockup />
            {onToggleCollapse && (
              <button
                type="button"
                onClick={onToggleCollapse}
                aria-label={tc("sidebar.collapse")}
                title={tc("sidebar.collapse")}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-transparent text-[var(--muted-foreground)] transition-colors duration-base ease-google hover:border-[var(--sidebar-border)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-foreground)]"
              >
                <PanelLeftClose size={17} />
              </button>
            )}
          </>
        )}
      </div>

      {/* Navigation */}
      <nav
        className={cn(
          "flex-1 space-y-0.5 overflow-y-auto py-3",
          // Collapsed 64px rail: the aside's 1px right border leaves 63px of
          // content, so 13.5/12.5 gutters + the row's 10px padding center both
          // the 17px icon and its 37px row box on the rail centerline.
          collapsed ? "pl-[13.5px] pr-[12.5px]" : "px-2.5",
        )}
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
                <NavPendingBar />
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

      {/* Theme control footer; language lives on the settings page only. */}
      <div
        className={cn(
          "border-t border-[var(--sidebar-border)]",
          collapsed ? "px-1 pt-2" : "px-3 pb-2 pt-2",
        )}
      >
        <ThemeToggle collapsed={collapsed} />
      </div>
    </>
  );
}
