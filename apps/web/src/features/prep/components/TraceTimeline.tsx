"use client";

/**
 * @file TraceTimeline.tsx
 * @description Merged thinking/tool-execution timeline in true arrival order.
 * Collapsed by default; expands to interleaved thinking blocks and tool steps,
 * each thinking block and tool step collapsible on its own (collapsed by default).
 */

import { memo, useMemo, useState } from "react";
import { Brain, ChevronRight, Shrink, Wrench } from "lucide-react";
import { useT, type MessageKey } from "@/i18n";
import { cn } from "@/lib/utils";
import type { PrepTraceItem } from "../types";

/** Tool name to label key; falls back to the raw name. */
const TOOL_LABEL_KEYS: Record<string, MessageKey<"prep">> = {
  web_search: "agent.tool.webSearch",
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
  github_list_commits: "agent.tool.githubListCommits",
  github_get_user: "agent.tool.githubGetUser",
  compact_context: "agent.tool.compactContext",
  search_tools: "agent.tool.searchTools",
};

function toolLabel(t: ReturnType<typeof useT>, name: string): string {
  const key = TOOL_LABEL_KEYS[name];
  return key ? t(key) : name;
}

/** Single-line shortening for previews. */
function shortenInline(text: string, limit = 48): string {
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

/** One thinking block with its own collapse toggle (collapsed by default). */
const ThinkingRow = memo(function ThinkingRow({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const body = useMemo(() => text.trim(), [text]);
  if (!body) return null;
  return (
    <li className="text-[11px] leading-relaxed">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-start gap-2 text-left"
      >
        <ChevronRight
          size={12}
          className={cn("mt-px shrink-0 text-ink-subtle transition-transform", open && "rotate-90")}
        />
        <Brain size={12} className="mt-px shrink-0 text-[var(--primary)]" />
        {!open && (
          <span className="min-w-0 flex-1 truncate text-ink-subtle">{shortenInline(body)}</span>
        )}
      </button>
      {open && (
        <pre className="mt-1 max-h-48 overflow-y-auto whitespace-pre-wrap pl-6 font-sans text-ink-subtle">
          {body}
        </pre>
      )}
    </li>
  );
});

/** One tool step with its own collapse toggle (collapsed by default). */
const ToolRow = memo(function ToolRow({
  name,
  query,
  args,
  result,
}: {
  name: string;
  query: string;
  args?: Record<string, string>;
  result?: string;
}) {
  const t = useT("prep");
  const [open, setOpen] = useState(false);
  const argEntries = useMemo(() => Object.entries(args ?? {}), [args]);
  return (
    <li className="text-[11px] leading-relaxed">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
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
  if (trace.length === 0) return null;

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
                name={item.name}
                query={item.query}
                args={item.args}
                result={item.result}
              />
            ) : item.kind === "compaction" ? (
              <CompactionRow key={`compact-${i}`} before={item.before} after={item.after} />
            ) : (
              <ThinkingRow key={`think-${i}`} text={item.text} />
            ),
          )}
        </ol>
      )}
    </div>
  );
});
