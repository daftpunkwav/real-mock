"use client";

/**
 * @file TraceTimeline.tsx
 * @description Merged thinking/tool-execution/compaction timeline in true
 * arrival order. Collapsed by default; expands to interleaved thinking blocks,
 * tool steps, and compaction events, each collapsible on its own (collapsed
 * by default).
 *
 * Row toggles are delegated to the container: streaming re-renders and the
 * follow-tail autoscroll can move a row between mousedown and mouseup, and a
 * browser only fires `click` on the common ancestor — the delegated handler
 * still resolves the intended row from the pointerdown-recorded toggle id,
 * where per-row listeners would silently miss.
 */

import { memo, useMemo, useRef, useState } from "react";
import { Brain, ChevronRight, Shrink, Wrench } from "lucide-react";
import { useT, type MessageKey } from "@/i18n";
import { cn } from "@/lib/utils";
import type { PrepTraceItem } from "../types";

/** Tool name to label key; falls back to the raw name. */
const TOOL_LABEL_KEYS: Record<string, MessageKey<"prep">> = {
  web_search: "agent.tool.webSearch",
  web_fetch: "agent.tool.webFetch",
  company_info: "agent.tool.companyInfo",
  quiz: "agent.tool.quiz",
  ask_user: "agent.tool.askUser",
  take_note: "agent.tool.takeNote",
  memory_list_tags: "agent.tool.memoryListTags",
  memory_list_summaries: "agent.tool.memoryListSummaries",
  memory_get_detail: "agent.tool.memoryGetDetail",
  memory_write: "agent.tool.memoryWrite",
  github_list_repos: "agent.tool.githubListRepos",
  github_get_readme: "agent.tool.githubGetReadme",
  github_get_repo: "agent.tool.githubGetRepo",
  github_get_file: "agent.tool.githubGetFile",
  github_list_commits: "agent.tool.githubListCommits",
  github_get_user: "agent.tool.githubGetUser",
  compact_context: "agent.tool.compactContext",
  search_tools: "agent.tool.searchTools",
  code_exec: "agent.tool.codeExec",
};

function toolLabel(t: ReturnType<typeof useT>, name: string): string {
  const key = TOOL_LABEL_KEYS[name];
  return key ? t(key) : name;
}

/** Single-line shortening for collapsed previews. Generous limit: the row
 * truncates visually via CSS ellipsis anyway, so this only bounds the DOM
 * text for very long streams (the old hard 48-char cut wasted the panel). */
function shortenInline(text: string, limit = 200): string {
  const flat = text.trim().replace(/\s+/g, " ");
  return flat.length > limit ? `${flat.slice(0, limit)}…` : flat;
}

/** Collapsed preview: the latest timeline entry. */
function previewText(t: ReturnType<typeof useT>, item: PrepTraceItem): string {
  if (item.kind === "tool") return `${toolLabel(t, item.name)}${item.query ? ` · ${item.query}` : ""}`;
  if (item.kind === "compaction") return t("trace.compaction", { before: item.before, after: item.after });
  return shortenInline(item.text);
}

/** One compaction event row (folded history, streamed like a tool step). */
const CompactionRow = memo(function CompactionRow({
  before,
  after,
}: {
  before: number;
  after: number;
}) {
  const t = useT("prep");
  return (
    <li className="flex items-center gap-2 text-[11px] leading-relaxed">
      <Shrink size={12} className="shrink-0 text-[var(--primary)]" />
      <span className="text-ink-muted">{t("trace.compaction", { before, after })}</span>
    </li>
  );
});

/** One thinking block. Expanded text continues inline after the icons and
 * wraps at the container width (the old layout pushed it to a separate
 * indented block, which read as a broken line). */
const ThinkingRow = memo(function ThinkingRow({
  text,
  open,
  rowId,
}: {
  text: string;
  open: boolean;
  rowId: string;
}) {
  const body = useMemo(() => text.trim(), [text]);
  if (!body) return null;
  return (
    <li className="text-[11px] leading-relaxed">
      <button
        type="button"
        data-trace-toggle={rowId}
        aria-expanded={open}
        className="flex w-full items-start gap-2 text-left"
      >
        <ChevronRight
          size={12}
          className={cn("mt-px shrink-0 text-ink-subtle transition-transform", open && "rotate-90")}
        />
        <Brain size={12} className="mt-px shrink-0 text-[var(--primary)]" />
        <span
          className={cn(
            "min-w-0 flex-1 text-ink-subtle",
            // Mutually exclusive: pre-wrap on a collapsed row fights truncate's
            // nowrap (whichever lands later in the stylesheet wins) and the
            // preview wraps into a line and a half.
            open ? "whitespace-pre-wrap break-words" : "truncate",
          )}
        >
          {open ? body : shortenInline(body)}
        </span>
      </button>
    </li>
  );
});

/** One tool step; expanded detail stays a panel below the summary row. */
const ToolRow = memo(function ToolRow({
  name,
  query,
  args,
  result,
  open,
  rowId,
}: {
  name: string;
  query: string;
  args?: Record<string, string>;
  result?: string;
  open: boolean;
  rowId: string;
}) {
  const t = useT("prep");
  const argEntries = useMemo(() => Object.entries(args ?? {}), [args]);
  return (
    <li className="text-[11px] leading-relaxed">
      <button
        type="button"
        data-trace-toggle={rowId}
        aria-expanded={open}
        className="flex w-full items-start gap-2 text-left"
      >
        <ChevronRight
          size={12}
          className={cn("mt-px shrink-0 text-ink-subtle transition-transform", open && "rotate-90")}
        />
        <span className="mt-px shrink-0 rounded bg-[var(--info-soft)] px-1.5 py-0.5 font-medium text-[var(--info-ink)]">
          {toolLabel(t, name)}
        </span>
        {query ? (
          <span className="min-w-0 flex-1 truncate text-ink-subtle" title={query}>
            {query}
          </span>
        ) : null}
      </button>
      {open && (
        <div className="mt-1 space-y-1.5 pl-6">
          <p className="font-mono text-ink-subtle">
            <span className="font-sans font-medium text-ink-muted">{t("trace.rawName")} </span>
            {name}
          </p>
          {argEntries.length > 0 && (
            <div>
              <p className="font-medium text-ink-muted">{t("trace.detailArgs")}</p>
              <pre className="mt-0.5 max-h-40 overflow-y-auto whitespace-pre-wrap rounded bg-surface-muted px-2 py-1.5 font-mono text-ink-subtle">
                {JSON.stringify(Object.fromEntries(argEntries), null, 2)}
              </pre>
            </div>
          )}
          {result ? (
            <div>
              <p className="font-medium text-ink-muted">{t("trace.detailResult")}</p>
              <pre className="mt-0.5 max-h-64 overflow-y-auto whitespace-pre-wrap rounded bg-surface-muted px-2 py-1.5 font-sans text-ink-subtle">
                {result}
              </pre>
            </div>
          ) : null}
        </div>
      )}
    </li>
  );
});

export const TraceTimeline = memo(function TraceTimeline({
  trace,
  streaming = false,
}: {
  trace: PrepTraceItem[];
  streaming?: boolean;
}) {
  const t = useT("prep");
  const [expanded, setExpanded] = useState(false);
  const [openRows, setOpenRows] = useState<ReadonlySet<string>>(new Set());
  /** Toggle id captured at pointerdown: survives the row moving under the
   * cursor between mousedown and mouseup (stream autoscroll, height jumps). */
  const pendingToggleRef = useRef<string | null>(null);
  if (trace.length === 0) return null;

  const toggle = (id: string | null) => {
    if (!id) return;
    if (id === "main") {
      setExpanded((v) => !v);
      return;
    }
    setOpenRows((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div
      className="overflow-hidden rounded-md border border-surface-border bg-surface-alt"
      onPointerDownCapture={(e) => {
        pendingToggleRef.current =
          (e.target as HTMLElement)
            .closest?.("[data-trace-toggle]")
            ?.getAttribute("data-trace-toggle") ?? null;
      }}
      onClick={(e) => {
        // Target first: keyboard-activated clicks have no pointerdown, and the
        // stale pointerdown of an abandoned press would otherwise toggle the
        // wrong row. The pointerdown record is the fallback for a press whose
        // row moved between mousedown and mouseup (target = common ancestor).
        const id =
          (e.target as HTMLElement)
            .closest?.("[data-trace-toggle]")
            ?.getAttribute("data-trace-toggle") ??
          pendingToggleRef.current ??
          null;
        pendingToggleRef.current = null;
        toggle(id);
      }}
    >
      <button
        type="button"
        data-trace-toggle="main"
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[11px] text-ink-muted transition-colors hover:bg-surface-muted"
        aria-expanded={expanded}
      >
        <ChevronRight
          size={13}
          className={cn("shrink-0 text-ink-subtle transition-transform", expanded && "rotate-90")}
        />
        <Wrench size={12} className="shrink-0 text-[var(--primary)]" />
        <span className="font-medium">{t("trace.title")}</span>
        {!expanded && (
          <span className="min-w-0 flex-1 truncate text-ink-subtle">
            {previewText(t, trace[trace.length - 1]!)}
          </span>
        )}
        {streaming && (
          <span className="ml-auto h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-[var(--primary)]" />
        )}
      </button>
      {expanded && (
        <ol className="space-y-2 border-t border-surface-border px-3 py-2.5">
          {trace.map((item, i) =>
            item.kind === "tool" ? (
              <ToolRow
                key={`tool-${i}`}
                rowId={`tool-${i}`}
                name={item.name}
                query={item.query}
                args={item.args}
                result={item.result}
                open={openRows.has(`tool-${i}`)}
              />
            ) : item.kind === "compaction" ? (
              <CompactionRow key={`compact-${i}`} before={item.before} after={item.after} />
            ) : (
              <ThinkingRow
                key={`think-${i}`}
                rowId={`think-${i}`}
                text={item.text}
                open={openRows.has(`think-${i}`)}
              />
            ),
          )}
        </ol>
      )}
    </div>
  );
});
