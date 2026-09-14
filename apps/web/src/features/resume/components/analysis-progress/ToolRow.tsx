"use client";

/**
 * @file ToolRow
 * @description Collapsible tool-call row (arguments, results, hosts).
 */

import { ChevronRight, Globe, Plug } from "lucide-react";
import { useT, type Translator } from "@/i18n";
import { cn } from "@/lib/utils";
import type { ReviewToolItem } from "../../reviewProgress";

function toolDescription(name: string, t: Translator<"resume">): string {
  const key = `stage.toolName.${name}`;
  return t.has(key) ? t(key) : t("stage.toolFallback");
}

export function ToolRow({
  item,
  expanded,
  onToggle,
}: {
  item: ReviewToolItem;
  expanded: boolean;
  onToggle: () => void;
}) {
  const t = useT("resume");
  const running = item.status === "running";
  const failed = item.status === "error";
  const sites = item.sites ?? [];
  const argsText = item.args ? JSON.stringify(item.args, null, 2) : "";
  const Icon = item.name.includes("search") ? Globe : Plug;
  const description = toolDescription(item.name, t);

  return (
    <div className="rounded-md">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full items-start gap-2 rounded-md px-1.5 py-1.5 text-left transition-colors hover:bg-surface-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]"
      >
        <ChevronRight
          size={13}
          className={cn("mt-0.5 shrink-0 text-ink-subtle transition-transform", expanded && "rotate-90")}
        />
        <Icon
          size={13}
          className={cn(
            "mt-0.5 shrink-0",
            failed ? "text-[var(--danger-ink)]" : "text-[var(--info-ink)]",
          )}
        />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <span className="text-[12px] text-ink">{description}</span>
            {item.query && item.query !== item.name ? (
              <span className="truncate text-[12px] text-ink-muted">{item.query}</span>
            ) : null}
            <span
              className={cn(
                "text-[11px]",
                running && "text-[var(--primary-ink)]",
                failed && "text-[var(--danger-ink)]",
                !running && !failed && "text-ink-subtle",
              )}
            >
              {running
                ? t("stage.toolStatus.running")
                : failed
                  ? t("stage.toolStatus.error")
                  : t("stage.toolStatus.done")}
            </span>
          </span>
          {sites.length > 0 ? (
            <span className="mt-1 flex flex-wrap gap-1" aria-label={t("stage.sites")}>
              {sites.map((host) => (
                <span
                  key={host}
                  className="rounded-sm bg-[var(--info-soft)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--info-ink)]"
                >
                  {host}
                </span>
              ))}
            </span>
          ) : null}
        </span>
      </button>
      {expanded ? (
        <div className="mb-1 ml-6 space-y-2 border-l border-surface-border pl-3">
          <div>
            <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-ink-subtle">
              {t("stage.toolName")}
            </p>
            <p className="mt-0.5 font-mono text-[11px] text-[var(--info-ink)]">{item.name}</p>
          </div>
          {argsText ? (
            <div>
              <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-ink-subtle">
                {t("stage.args")}
              </p>
              <pre className="mt-0.5 max-h-40 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-ink-subtle">
                {argsText}
              </pre>
            </div>
          ) : null}
          {item.result ? (
            <div>
              <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-ink-subtle">
                {t("stage.result")}
              </p>
              <pre className="mt-0.5 max-h-56 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-ink-subtle">
                {item.result}
              </pre>
            </div>
          ) : running ? (
            <p className="text-[11px] text-ink-subtle">{t("stage.toolStatus.running")}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
