"use client";

import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type ComponentType,
} from "react";
import { ChevronDown, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface CollapsibleSectionProps {
  title: string;
  icon: LucideIcon | ComponentType<{ size?: number; className?: string; strokeWidth?: number }>;
  hint?: string;
  /** Initial state in uncontrolled mode; use open for controlled mode. */
  defaultOpen?: boolean;
  /** Optional controlled open state. */
  open?: boolean;
  onOpenChange?: (next: boolean) => void;
  children: ReactNode;
  /** Visual tone, such as danger, warning, or brand. */
  tone?: "brand" | "success" | "warning" | "danger" | "neutral";
  /** Optional action area displayed on the right. */
  actions?: ReactNode;
  className?: string;
}

const TONE_MAP = {
  brand: "icon-badge icon-badge-brand",
  success: "icon-badge icon-badge-success",
  warning: "icon-badge icon-badge-warning",
  danger: "icon-badge icon-badge-danger",
  neutral: "icon-badge icon-badge-muted",
} as const;

export function CollapsibleSection({
  title,
  icon: Icon,
  hint,
  defaultOpen = true,
  open,
  onOpenChange,
  children,
  tone = "brand",
  actions,
  className,
}: CollapsibleSectionProps) {
  const [inner, setInner] = useState(defaultOpen);
  const isControlled = open !== undefined;
  const isOpen = isControlled ? open : inner;
  const bodyRef = useRef<HTMLDivElement>(null);
  const [maxHeight, setMaxHeight] = useState<string>(
    defaultOpen ? "none" : "0px",
  );

  const toggle = () => {
    const next = !isOpen;
    if (!isControlled) setInner(next);
    onOpenChange?.(next);
  };

  // Remeasure content when toggled so height changes animate smoothly.
  useEffect(() => {
    const node = bodyRef.current;
    if (!node) return;
    if (isOpen) {
      // Animate to the measured height, then release the cap for later content changes.
      const target = `${node.scrollHeight}px`;
      setMaxHeight(target);
      const t = window.setTimeout(() => setMaxHeight("none"), 220);
      return () => window.clearTimeout(t);
    } else {
      // Lock the current pixel height before transitioning to zero.
      const current = `${node.scrollHeight}px`;
      setMaxHeight(current);
      requestAnimationFrame(() => setMaxHeight("0px"));
    }
  }, [isOpen, children]);

  const iconCls = TONE_MAP[tone] ?? TONE_MAP.brand;

  return (
    <section className={cn("surface-card overflow-hidden", className)}>
      <header
        className={cn(
          "flex items-center justify-between gap-3 border-b border-surface-border bg-surface-alt px-5 py-3.5 transition-colors",
          isOpen ? "" : "border-b-0",
        )}
      >
        <button
          type="button"
          onClick={toggle}
          aria-expanded={isOpen}
          aria-controls={`section-${title}`}
          className="flex min-w-0 flex-1 items-center gap-2.5 text-left transition-colors hover:text-[var(--primary)]"
        >
          <span className={iconCls}>
            <Icon size={15} strokeWidth={1.75} />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-[14px] font-semibold leading-snug tracking-tight text-ink">
              {title}
            </h2>
            {hint && isOpen && (
              <p className="mt-0.5 text-[11px] leading-snug text-ink-subtle">{hint}</p>
            )}
          </div>
          <ChevronDown
            size={16}
            className={cn(
              "shrink-0 text-ink-subtle transition-transform duration-base ease-google",
              isOpen ? "rotate-0" : "-rotate-90",
            )}
          />
        </button>
        {actions && (
          <div
            className="flex shrink-0 items-center gap-2"
            onClick={(e) => e.stopPropagation()}
          >
            {actions}
          </div>
        )}
      </header>

      <div
        id={`section-${title}`}
        role="region"
        aria-hidden={!isOpen}
        style={{
          maxHeight,
          opacity: isOpen ? 1 : 0,
          overflow: "hidden",
          transition: "max-height var(--dur-slow) var(--ease), opacity var(--dur-slow) var(--ease)",
        }}
      >
        <div ref={bodyRef} className="p-5">
          {children}
        </div>
      </div>
    </section>
  );
}
