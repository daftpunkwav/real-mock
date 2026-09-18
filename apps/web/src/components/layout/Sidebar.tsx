"use client";

/** Responsive sidebar shell: mobile top bar/drawer, desktop collapse state, and drag-to-resize width. */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useT } from "@/i18n";
import { LogoMark } from "@/components/brand/LogoMark";
import { NavContent } from "./SidebarNav";
import {
  SIDEBAR_DEFAULT_WIDTH,
  SIDEBAR_MAX_WIDTH,
  SIDEBAR_MIN_WIDTH,
  writeSidebarState,
} from "./sidebarStorage";

const DEFAULT_WIDTH = SIDEBAR_DEFAULT_WIDTH;
const MIN_WIDTH = SIDEBAR_MIN_WIDTH;
const MAX_WIDTH = SIDEBAR_MAX_WIDTH;
/** Dragging the edge below this width snaps the sidebar into the collapsed rail. */
const COLLAPSE_THRESHOLD = 170;

export function Sidebar({
  initialCollapsed = false,
  initialWidth = DEFAULT_WIDTH,
}: {
  initialCollapsed?: boolean;
  initialWidth?: number;
}) {
  const pathname = usePathname();
  const t = useT("common");
  const [collapsed, setCollapsed] = useState(initialCollapsed);
  const [width, setWidth] = useState(initialWidth);
  const [resizing, setResizing] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const asideRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    writeSidebarState({ collapsed, width });
  }, [collapsed, width]);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!mobileOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [mobileOpen]);

  // Lock the cursor and text selection for the whole drag gesture.
  useEffect(() => {
    if (!resizing) return;
    const prevCursor = document.body.style.cursor;
    const prevSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    return () => {
      document.body.style.cursor = prevCursor;
      document.body.style.userSelect = prevSelect;
    };
  }, [resizing]);

  const applyDragWidth = (e: ReactPointerEvent<HTMLDivElement>) => {
    const left = asideRef.current?.getBoundingClientRect().left ?? 0;
    const next = e.clientX - left;
    if (next < COLLAPSE_THRESHOLD) {
      setCollapsed(true);
    } else {
      setCollapsed(false);
      setWidth(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, next)));
    }
  };

  return (
    <>
      {/* Mobile top bar */}
      <div className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b border-surface-border bg-surface-card/95 px-4 backdrop-blur-md lg:hidden">
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="btn-ghost !h-9 !w-9"
          aria-label={t("sidebar.openNav")}
        >
          <Menu size={18} />
        </button>
        <Link href="/" className="flex items-center gap-2">
          <LogoMark size={20} />
          <span className="text-[14px] font-semibold text-ink">Real Mock</span>
        </Link>
      </div>

      {/* Mobile backdrop */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            className="fixed inset-0 z-40 bg-black/40 lg:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setMobileOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* Mobile drawer */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.aside
            className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-[var(--sidebar-border)] bg-[var(--sidebar)] shadow-lg lg:hidden"
            initial={{ x: -288 }}
            animate={{ x: 0 }}
            exit={{ x: -288 }}
            transition={{ type: "spring", stiffness: 420, damping: 38 }}
          >
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="btn-ghost absolute right-3 top-3 !h-8 !w-8"
              aria-label={t("sidebar.closeNav")}
            >
              <X size={16} />
            </button>
            <NavContent collapsed={false} onNavigate={() => setMobileOpen(false)} />
          </motion.aside>
        )}
      </AnimatePresence>

      {/* Desktop sidebar */}
      <motion.aside
        ref={asideRef}
        className="sticky top-0 z-20 hidden h-screen shrink-0 flex-col border-r border-[var(--sidebar-border)] bg-[var(--sidebar)] lg:flex"
        initial={false}
        animate={{ width: collapsed ? 64 : width }}
        transition={
          resizing && !collapsed
            ? { duration: 0 }
            : { duration: 0.22, ease: [0.2, 0, 0, 1] }
        }
      >
        <NavContent
          collapsed={collapsed}
          onToggleCollapse={() => setCollapsed((v) => !v)}
        />

        {/* Drag handle on the right edge to resize; dragging far left collapses */}
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label={t("sidebar.resize")}
          className="group/handle absolute inset-y-0 -right-1 z-30 w-2 cursor-col-resize touch-none"
          onPointerDown={(e) => {
            e.preventDefault();
            e.currentTarget.setPointerCapture(e.pointerId);
            setResizing(true);
          }}
          onPointerMove={(e) => {
            if (e.currentTarget.hasPointerCapture(e.pointerId)) applyDragWidth(e);
          }}
          onPointerUp={(e) => {
            if (e.currentTarget.hasPointerCapture(e.pointerId)) {
              e.currentTarget.releasePointerCapture(e.pointerId);
            }
            setResizing(false);
          }}
          onPointerCancel={() => setResizing(false)}
        >
          <div
            className={cn(
              "mx-auto h-full w-[2px] transition-colors duration-base ease-google",
              resizing
                ? "bg-[var(--primary)]"
                : "bg-transparent group-hover/handle:bg-[var(--primary)]/40",
            )}
          />
        </div>
      </motion.aside>
    </>
  );
}
