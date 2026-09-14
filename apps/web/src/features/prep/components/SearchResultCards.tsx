"use client";

/**
 * @file SearchResultCards.tsx
 * @description Collapsible web-search citation cards (one group per tool query).
 */

import { memo, useState } from "react";
import { ChevronRight, ExternalLink, Search } from "lucide-react";
import { useT } from "@/i18n";
import { safeAbsoluteHttpUrl } from "@/components/markdownSafeUrl";
import type { PrepSearchGroup } from "@/lib/api/contract";

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** Collapsible web-search citation cards (one group per tool query). */
export const SearchResultCards = memo(function SearchResultCards({
  groups,
  defaultExpanded = false,
}: {
  groups: PrepSearchGroup[];
  /** Pre-expand on mount (collapsed by default; tests force it open). */
  defaultExpanded?: boolean;
}) {
  const t = useT("prep");
  const [expanded, setExpanded] = useState(defaultExpanded);
  const visible = groups.filter((g) => (g.results?.length ?? 0) > 0);
  const total = visible.reduce((acc, g) => acc + (g.results?.length ?? 0), 0);
  if (visible.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-md border border-surface-border bg-surface-alt">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[11px] text-ink-muted transition-colors hover:bg-surface-muted"
        aria-expanded={expanded}
      >
        <ChevronRight
          size={13}
          className={`shrink-0 text-ink-subtle transition-transform ${expanded ? "rotate-90" : ""}`}
        />
        <Search size={12} className="shrink-0 text-[var(--primary)]" />
        <span className="shrink-0 font-medium">
          {t("resources.sourcesSummary", { total, groups: visible.length })}
        </span>
        {!expanded && (
          <span className="min-w-0 flex-1 truncate text-ink-subtle" title={visible[0]!.query}>
            {visible.map((g) => g.query).filter(Boolean).join(" / ")}
          </span>
        )}
      </button>
      {expanded && (
        <div className="space-y-3 border-t border-surface-border px-3 py-2.5">
          {visible.map((group) => (
            <div key={group.query || group.results?.[0]?.url} className="space-y-1.5">
              {group.query ? (
                <p className="truncate text-[11px] text-ink-subtle" title={group.query}>
                  {t("resources.queryLabel", { query: group.query })}
                </p>
              ) : null}
              <ul className="space-y-1.5">
                {(group.results ?? []).map((hit, idx) => {
                  const href = safeAbsoluteHttpUrl(hit.url);
                  const inner = (
                    <div className="flex items-start gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="line-clamp-2 text-[13px] font-medium leading-snug text-[var(--info-ink)]">
                          {hit.title}
                        </p>
                        <p className="mt-0.5 truncate text-[11px] text-ink-subtle">
                          {hostOf(hit.url)}
                        </p>
                        {hit.snippet ? (
                          <p className="mt-1 line-clamp-2 text-[12px] leading-relaxed text-ink-muted">
                            {hit.snippet}
                          </p>
                        ) : null}
                      </div>
                      {href ? (
                        <ExternalLink
                          size={13}
                          className="mt-0.5 shrink-0 text-ink-subtle"
                          aria-hidden
                        />
                      ) : null}
                    </div>
                  );
                  return (
                    <li key={`${idx}-${hit.url}`}>
                      {href ? (
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer nofollow"
                          className="block rounded-md border border-surface-border bg-surface px-3 py-2 transition-colors hover:border-[var(--primary)] hover:bg-[var(--info-soft)]"
                        >
                          {inner}
                        </a>
                      ) : (
                        <div className="block rounded-md border border-surface-border bg-surface px-3 py-2">
                          {inner}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
});
