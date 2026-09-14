/**
 * @file useUnsavedNavigation
 * @description Guard against leaving the page with unsaved edits.
 *
 * Responsibilities:
 * - beforeunload for refresh / tab close
 * - Capture-phase intercept of in-app <a href="/..."> clicks
 * - Confirm stay vs leave via pendingNav + router.push
 * - Drop pendingNav when dirty becomes false (reverted edits or completed save)
 *
 * Must not own profile data or save logic.
 * Does not cover browser back/forward, Shadow DOM, or imperative router.push
 * from other code. In-app links are document <a href> only (Next.js Link included).
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export function useUnsavedNavigation(dirty: boolean) {
  const router = useRouter();
  const [pendingNav, setPendingNav] = useState<string | null>(null);

  useEffect(() => {
    if (!dirty) return;
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      // Some engines honor returnValue only; set both.
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [dirty]);

  useEffect(() => {
    if (!dirty) return;
    const currentPath = window.location.pathname;
    const handleNavClick = (e: MouseEvent) => {
      const anchor = (e.target as HTMLElement | null)?.closest("a");
      const href = anchor?.getAttribute("href");
      if (!href?.startsWith("/") || href === currentPath) return;
      e.preventDefault();
      e.stopPropagation();
      setPendingNav(href);
    };
    document.addEventListener("click", handleNavClick, true);
    return () => document.removeEventListener("click", handleNavClick, true);
  }, [dirty]);

  useEffect(() => {
    if (!dirty) setPendingNav(null);
  }, [dirty]);

  const stayOnPage = useCallback(() => setPendingNav(null), []);

  // Capture the href before clearing state: the dirty-false effect also
  // calls setPendingNav(null), and React may replay updaters — do not push
  // from inside a setState updater.
  const leavePage = useCallback(() => {
    const target = pendingNav;
    setPendingNav(null);
    if (target) router.push(target);
  }, [router, pendingNav]);

  return { pendingNav, stayOnPage, leavePage };
}
