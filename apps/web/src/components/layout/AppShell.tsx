"use client";

import { usePathname } from "next/navigation";
import { isFixedHeightPathname, isFullscreenPathname } from "@/config/pageLayout";
import { Sidebar } from "./Sidebar";
import type { SidebarPersistedState } from "./sidebarStorage";

export function AppShell({
  children,
  sidebarInitial,
}: {
  children: React.ReactNode;
  sidebarInitial: SidebarPersistedState;
}) {
  const pathname = usePathname();
  const isFullscreen = isFullscreenPathname(pathname);
  const isFixedHeightPage = isFixedHeightPathname(pathname);

  // Fullscreen Page(such as an interview room)Returning users/System theme,Remove sidebar and scrolling container only
  if (isFullscreen) {
    return (
      <main className="h-screen w-screen overflow-hidden bg-[var(--background)] text-[var(--foreground)]">
        {children}
      </main>
    );
  }

  return (
    <div className="flex min-h-screen flex-col lg:flex-row bg-[var(--background)]">
      <Sidebar
        initialCollapsed={sidebarInitial.collapsed}
        initialWidth={sidebarInitial.width}
      />
      <main
        className={
          isFixedHeightPage
            ? "flex-1 min-h-0 lg:h-screen overflow-hidden"
            : "flex-1 overflow-y-auto [scrollbar-gutter:stable]"
        }
      >
        {children}
      </main>
    </div>
  );
}
