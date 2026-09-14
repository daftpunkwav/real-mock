"use client";

/**
 * @file Select.tsx
 * @description Project-styled dropdown select (custom listbox, no native popup).
 *
 * Matches the app's field/button tokens: 36px trigger with focus ring,
 * surface-card popover, primary check mark for the active option.
 * Keyboard: ArrowUp/ArrowDown to move, Enter to pick, Escape to dismiss.
 */

import { useCallback, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SelectOption<T extends string | number> {
  value: T;
  label: string;
}

/** Max popover height before internal scrolling kicks in. */
const POPOVER_MAX_HEIGHT = 240;
/** Gap between the trigger and the popover. */
const POPOVER_GAP = 4;
/** Option row height (h-9) — kept in sync with the row class below. */
const OPTION_ROW_HEIGHT = 36;
/** Popover vertical chrome: p-1 padding plus border. */
const POPOVER_CHROME_HEIGHT = 10;

export function Select<T extends string | number>({
  value,
  options,
  onChange,
  disabled = false,
  className,
  ariaLabel,
}: {
  value: T;
  options: SelectOption<T>[];
  onChange: (value: T) => void;
  disabled?: boolean;
  className?: string;
  ariaLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(() =>
    Math.max(
      0,
      options.findIndex((o) => o.value === value),
    ),
  );
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const [popoverStyle, setPopoverStyle] = useState<{
    left: number;
    top?: number;
    bottom?: number;
    width: number;
    maxHeight: number;
  } | null>(null);
  const listId = useId();

  const selectedIndex = options.findIndex((o) => o.value === value);
  const selected = options[selectedIndex];

  /**
   * Exact placement from current layout — no height estimates.
   * Content height is deterministic (fixed row height × option count), and
   * above-placement anchors by `bottom` so the popover always hugs the trigger.
   */
  const computePlacement = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    const needed = options.length * OPTION_ROW_HEIGHT + POPOVER_CHROME_HEIGHT;
    const spaceBelow = window.innerHeight - rect.bottom - POPOVER_GAP;
    const spaceAbove = rect.top - POPOVER_GAP;
    const width = Math.min(rect.width, window.innerWidth - 16);
    const left = Math.min(rect.left, Math.max(8, window.innerWidth - width - 8));
    if (spaceBelow >= needed || spaceBelow >= spaceAbove) {
      return {
        left,
        top: rect.bottom + POPOVER_GAP,
        bottom: undefined as number | undefined,
        width,
        maxHeight: Math.min(POPOVER_MAX_HEIGHT, Math.max(spaceBelow, 96)),
      };
    }
    return {
      left,
      top: undefined as number | undefined,
      bottom: window.innerHeight - rect.top + POPOVER_GAP,
      width,
      maxHeight: Math.min(POPOVER_MAX_HEIGHT, Math.max(spaceAbove, 96)),
    };
  }, [options.length]);

  const close = (refocus = false) => {
    setOpen(false);
    setPopoverStyle(null);
    if (refocus) triggerRef.current?.focus({ preventScroll: true });
  };

  const pick = (index: number) => {
    const option = options[index];
    if (!option) return;
    if (option.value !== value) onChange(option.value);
    close(true);
  };

  // Keep the popover anchored while it is open.
  useLayoutEffect(() => {
    if (!open) return;
    const onReposition = () => {
      const next = computePlacement();
      if (next) setPopoverStyle(next);
    };
    window.addEventListener("resize", onReposition);
    // Capture phase: any nested scroll container also re-anchors the popover.
    window.addEventListener("scroll", onReposition, true);
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node | null;
      if (
        target &&
        !triggerRef.current?.contains(target) &&
        !popRef.current?.contains(target)
      ) {
        close();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      window.removeEventListener("resize", onReposition);
      window.removeEventListener("scroll", onReposition, true);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [open, computePlacement]);

  const openMenu = (index?: number) => {
    setHighlight(index ?? (selectedIndex >= 0 ? selectedIndex : 0));
    // Layout is current inside event handlers, so place synchronously —
    // the popover mounts at its final position with no estimate flash.
    const placement = computePlacement();
    if (!placement) return;
    setPopoverStyle(placement);
    setOpen(true);
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={ariaLabel}
        aria-activedescendant={open ? `${listId}-${highlight}` : undefined}
        disabled={disabled}
        onClick={() => (open ? close() : openMenu())}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            if (!open) {
              openMenu();
            } else {
              setHighlight((h) =>
                e.key === "ArrowDown"
                  ? Math.min(options.length - 1, h + 1)
                  : Math.max(0, h - 1),
              );
            }
          } else if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            if (!open) openMenu();
            else pick(highlight);
          } else if (e.key === "Escape" && open) {
            e.preventDefault();
            close(true);
          }
        }}
        className={cn(
          "flex h-9 w-full items-center justify-between gap-2 rounded-[var(--radius)] border border-[var(--input)] bg-[var(--card)] px-3 text-[var(--text-sm)] text-ink transition-colors hover:border-[var(--border-strong)] focus:border-[var(--primary)] focus:outline-none focus:[box-shadow:var(--shadow-focus)] disabled:cursor-not-allowed disabled:opacity-60",
          className,
        )}
      >
        <span className="min-w-0 truncate">{selected?.label ?? ""}</span>
        <ChevronDown
          size={14}
          className={cn(
            "shrink-0 text-ink-subtle transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open &&
        popoverStyle &&
        createPortal(
          <div
            ref={popRef}
            id={listId}
            role="listbox"
            aria-label={ariaLabel}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                e.preventDefault();
                setHighlight((h) => {
                  const next =
                    e.key === "ArrowDown"
                      ? Math.min(options.length - 1, h + 1)
                      : Math.max(0, h - 1);
                  popRef.current
                    ?.querySelector(`[data-index="${next}"]`)
                    ?.scrollIntoView({ block: "nearest" });
                  return next;
                });
              } else if (e.key === "Enter") {
                e.preventDefault();
                pick(highlight);
              } else if (e.key === "Escape") {
                e.preventDefault();
                close(true);
              } else if (e.key === "Tab") {
                close();
              }
            }}
            className="surface-card fixed z-50 overflow-y-auto !p-1"
            style={{
              left: popoverStyle.left,
              top: popoverStyle.top,
              bottom: popoverStyle.bottom,
              width: popoverStyle.width,
              maxWidth: "calc(100vw - 16px)",
              maxHeight: popoverStyle.maxHeight,
            }}
          >
            {options.map((option, index) => {
              const active = option.value === value;
              const focused = index === highlight;
              return (
                <div
                  key={String(option.value)}
                  id={`${listId}-${index}`}
                  data-index={index}
                  role="option"
                  aria-selected={active}
                  onClick={() => pick(index)}
                  onMouseEnter={() => setHighlight(index)}
                  className={cn(
                    "flex h-9 cursor-pointer items-center justify-between gap-2 rounded-md px-2.5 text-[13px] transition-colors",
                    focused ? "bg-surface-muted" : "bg-transparent",
                    active ? "font-medium text-[var(--primary)]" : "text-ink",
                  )}
                >
                  <span className="min-w-0 truncate">{option.label}</span>
                  {active && <Check size={14} className="shrink-0" />}
                </div>
              );
            })}
          </div>,
          document.body,
        )}
    </>
  );
}
