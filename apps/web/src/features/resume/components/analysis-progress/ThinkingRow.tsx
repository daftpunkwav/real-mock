"use client";

/**
 * @file ThinkingRow
 * @description Collapsible thinking row for the live review log.
 */

import { Brain, ChevronRight } from "lucide-react";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";
import type { ReviewThinkingItem } from "../../reviewProgress";

function thinkingSeconds(item: ReviewThinkingItem, now: number): number {
  const end = item.endedAt ?? now;
  return Math.max(0, Math.round((end - item.startedAt) / 1000));
}

export function ThinkingRow({
  item,
  now,
  expanded,
  onToggle,
}: {
  item: ReviewThinkingItem;
  now: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  const t = useT("resume");
  const active = item.endedAt == null;
  const seconds = thinkingSeconds(item, now);
  const body = item.content.replace(/^\s+/, "");
  const duration =
    seconds > 0 ? t("stage.thinkingDuration", { seconds: active ? seconds : Math.max(1, seconds) }) : "";
  const label = active ? t("stage.thinkingActive") : t("stage.thinking");

  return (
    <div className="rounded-md border border-transparent">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full items-center gap-2 rounded-md px-1.5 py-1.5 text-left text-[12px] text-ink-muted transition-colors hover:bg-surface-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]"
      >
        <ChevronRight
          size={13}
          className={cn("shrink-0 text-ink-subtle transition-transform", expanded && "rotate-90")}
        />
        <Brain size={13} className="shrink-0 text-[var(--primary)]" />
        <span className="font-medium">{label}</span>
        {duration ? <span className="text-ink-subtle">· {duration}</span> : null}
        {active ? (
          <span className="ml-auto h-1.5 w-1.5 shrink-0 motion-safe:animate-pulse rounded-full bg-[var(--primary)]" />
        ) : null}
      </button>
      {expanded ? (
        <pre className="mb-1 ml-6 max-h-48 overflow-y-auto whitespace-pre-wrap border-l border-surface-border pl-3 font-mono text-[11px] leading-relaxed text-ink-subtle">
          {body || "…"}
          {active ? (
            <span className="ml-0.5 inline-block h-3 w-1 motion-safe:animate-pulse bg-ink-subtle align-middle" />
          ) : null}
        </pre>
      ) : null}
    </div>
  );
}
