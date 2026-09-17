"use client";

/**
 * @file Select.tsx
 * @description Project-styled dropdown select (anchored popover, no portal).
 *
 * The popover is absolutely positioned inside the trigger's wrapper, so it
 * follows document scroll natively — no fixed-position re-anchor loop, no
 * flicker during fast scrolling. Opens downward when there is room below the
 * trigger, otherwise upward. Keyboard: ArrowUp/ArrowDown to move, Enter to
 * pick, Escape to dismiss.
 */

import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SelectOption<T extends string | number> {
  value: T;
  label: string;
}

/** Max popover height before internal scrolling kicks in. */
const POPOVER_MAX_HEIGHT = 240;
/** Estimated per-option height used for the open-direction decision. */
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
  const [openUp, setOpenUp] = useState(false);
  const [highlight, setHighlight] = useState(() =>
    Math.max(
      0,
      options.findIndex((o) => o.value === value),
    ),
  );
  const wrapperRef = useRef<HTMLSpanElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  const selectedIndex = options.findIndex((o) => o.value === value);
  const selected = options[selectedIndex];

  // Open toward the side with more room; the popover then scrolls with the
  // document, so no repositioning is ever needed while it stays open.
  const openMenu = (index?: number) => {
    setHighlight(index ?? (selectedIndex >= 0 ? selectedIndex : 0));
    const el = wrapperRef.current;
    if (el) {
      const rect = el.getBoundingClientRect();
      const needed = Math.min(
        POPOVER_MAX_HEIGHT,
        options.length * OPTION_ROW_HEIGHT + POPOVER_CHROME_HEIGHT,
      );
      setOpenUp(window.innerHeight - rect.bottom < needed && rect.top > window.innerHeight - rect.bottom);
    }
    setOpen(true);
  };

  const pick = (index: number) => {
    const option = options[index];
    if (!option) return;
    if (option.value !== value) onChange(option.value);
    setOpen(false);
  };

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node | null;
      if (target && !wrapperRef.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  return (
    <span ref={wrapperRef} className="relative inline-flex w-full">
      <button
        type="button"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={ariaLabel}
        aria-activedescendant={open ? `${listId}-${highlight}` : undefined}
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : openMenu())}
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
            setOpen(false);
          }
        }}
        className={cn(
          "flex h-9 w-full items-center justify-between gap-2 rounded-[var(--radius)] border border-[var(--border-strong)] bg-[var(--card)] px-3 text-[var(--text-sm)] text-ink transition-colors hover:border-[var(--primary)] focus:border-[var(--primary)] focus:outline-none focus:[box-shadow:var(--shadow-focus)] disabled:cursor-not-allowed disabled:opacity-60",
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
      {open && (
        <div
          ref={listRef}
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
                listRef.current
                  ?.querySelector(`[data-index="${next}"]`)
                  ?.scrollIntoView({ block: "nearest" });
                return next;
              });
            } else if (e.key === "Enter") {
              e.preventDefault();
              pick(highlight);
            } else if (e.key === "Escape") {
              e.preventDefault();
              setOpen(false);
            } else if (e.key === "Tab") {
              setOpen(false);
            }
          }}
          className={cn(
            "surface-card absolute left-0 z-30 max-h-60 w-full min-w-[120px] overflow-y-auto !p-1",
            openUp ? "bottom-full mb-1" : "top-full mt-1",
          )}
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
        </div>
      )}
    </span>
  );
}
