/**
 * @file reviewProgress.ts
 * @description Live Agent-plan + chronological execution log for a deep review.
 */

import type {
  ResumeAnalyzeSSEEvent,
  ReviewPlanStatus,
  ReviewPlanStep,
  ReviewToolStatus,
} from "@/lib/api/resumeAnalyzeEvents";

export type { ReviewPlanStatus, ReviewPlanStep, ReviewToolStatus };

const THINKING_MAX_CHARS = 24_000;
// Must match backend agents/process.py PLAN_TOOL_PREFIX; plan tools are
// folded into the plan spine, never rendered as timeline rows.
const PLAN_TOOL_PREFIX = "review_";

export type ReviewThinkingItem = {
  kind: "thinking";
  id: string;
  content: string;
  startedAt: number;
  endedAt?: number;
};

export type ReviewToolItem = {
  kind: "tool";
  id: string;
  name: string;
  query?: string;
  status: ReviewToolStatus;
  args?: Record<string, unknown>;
  result?: string;
  sites?: string[];
};

export type ReviewNoticeItem = {
  kind: "notice";
  id: string;
  content: string;
  startedAt: number;
};

export type ReviewTimelineItem = ReviewThinkingItem | ReviewToolItem | ReviewNoticeItem;

export interface ReviewLiveState {
  steps: ReviewPlanStep[];
  timeline: ReviewTimelineItem[];
}

function asToolStatus(value: unknown, hasResult: boolean): ReviewToolStatus {
  if (value === "done" || value === "error" || value === "running") return value;
  return hasResult ? "done" : "running";
}

function closeOpenThinking(
  timeline: ReviewTimelineItem[],
  now: number,
): ReviewTimelineItem[] {
  const last = timeline[timeline.length - 1];
  if (!last || last.kind !== "thinking" || last.endedAt != null) return timeline;
  return [...timeline.slice(0, -1), { ...last, endedAt: now }];
}

function clipThinking(content: string): string {
  return content.length <= THINKING_MAX_CHARS ? content : content.slice(-THINKING_MAX_CHARS);
}

/** Drop round-separator newlines so a new thinking row does not open with blank lines. */
function appendThinking(prev: string, chunk: string): string {
  const next = chunk.replace(/^\n+/, "");
  if (!next.trim()) return prev;
  if (!prev.trim()) return next.replace(/^\s+/, "");
  return prev + next;
}

function sitesOf(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const hosts = value.filter((item): item is string => typeof item === "string" && item.length > 0);
  return hosts.length ? hosts : undefined;
}

function argsOf(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  return value as Record<string, unknown>;
}

/** Fold SSE events into plan + a thinking/tool timeline in occurrence order. */
export function applyAnalyzeEvent(
  prev: ReviewLiveState | undefined,
  event: ResumeAnalyzeSSEEvent,
  now = Date.now(),
): ReviewLiveState {
  const current: ReviewLiveState = prev ?? { steps: [], timeline: [] };

  if (event.type === "plan" && Array.isArray(event.steps)) {
    // Drop malformed entries (null / non-object): PlanSpine reads step fields
    // directly, so one corrupted row must not crash the whole progress view.
    const steps = event.steps.filter(
      (step): step is ReviewPlanStep => Boolean(step) && typeof step === "object",
    );
    return { ...current, steps };
  }

  if (event.type === "thinking") {
    const chunk = typeof event.content === "string" ? event.content : "";
    if (!chunk.trim()) return current;
    const last = current.timeline[current.timeline.length - 1];
    if (last?.kind === "thinking" && last.endedAt == null) {
      const next: ReviewThinkingItem = {
        ...last,
        content: clipThinking(appendThinking(last.content, chunk)),
      };
      return { ...current, timeline: [...current.timeline.slice(0, -1), next] };
    }
    const item: ReviewThinkingItem = {
      kind: "thinking",
      id: `think-${current.timeline.length + 1}`,
      content: clipThinking(appendThinking("", chunk)),
      startedAt: now,
    };
    return { ...current, timeline: [...current.timeline, item] };
  }

  if (event.type === "notice") {
    const content = typeof event.message === "string" ? event.message.trim() : "";
    if (!content) return current;
    const closed = closeOpenThinking(current.timeline, now);
    const item: ReviewNoticeItem = {
      kind: "notice",
      id: `notice-${closed.length + 1}`,
      content,
      startedAt: now,
    };
    return { ...current, timeline: [...closed, item] };
  }

  if (event.type === "tool_step" && event.name) {
    if (event.name.startsWith(PLAN_TOOL_PREFIX)) {
      return current;
    }
    const closed = closeOpenThinking(current.timeline, now);
    const status = asToolStatus(event.status, Boolean(event.result));
    const sites = sitesOf(event.sites);
    const args = argsOf(event.args);
    const existingIndex = event.id
      ? closed.findIndex((item) => item.kind === "tool" && item.id === event.id)
      : -1;
    if (existingIndex >= 0) {
      const previous = closed[existingIndex] as ReviewToolItem;
      const updated: ReviewToolItem = {
        ...previous,
        name: event.name,
        query: event.query || previous.query,
        status,
        args: args ?? previous.args,
        result: event.result ?? previous.result,
        sites: sites ?? previous.sites,
      };
      const timeline = [...closed];
      timeline[existingIndex] = updated;
      return { ...current, timeline };
    }
    const item: ReviewToolItem = {
      kind: "tool",
      id: event.id || `tool-${event.name}-${closed.length + 1}`,
      name: event.name,
      query: event.query || "",
      status,
      args,
      result: event.result,
      sites,
    };
    return { ...current, timeline: [...closed, item] };
  }

  return current;
}
