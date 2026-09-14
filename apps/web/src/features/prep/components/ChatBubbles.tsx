/**
 * @file ChatBubbles.tsx
 * @description Prep chat bubbles: assistant (status, trace timeline, search
 * cards, answer, stopped badge, action bar) and user (content, action bar).
 */

import { memo } from "react";
import { Bot, OctagonX, User } from "lucide-react";
import { useT } from "@/i18n";
import { MarkdownContent } from "@/components/MarkdownContent";
import type { PrepChatMessage } from "../types";
import { useMonotonicWidth } from "../hooks/useMonotonicWidth";
import { SearchResultCards } from "./SearchResultCards";
import { ThinkAnswerMessage } from "./ThinkAnswerMessage";
import { TraceTimeline } from "./TraceTimeline";
import { AssistantMessageActions, UserMessageActions } from "./MessageActions";

export interface AssistantBubbleActions {
  onExport: (msg: PrepChatMessage) => void;
  /** Absent for stale archives whose backup was retired (fork would 404). */
  onFork?: (msg: PrepChatMessage) => void;
  onRegenerate?: (msg: PrepChatMessage) => void;
  onRate?: (msg: PrepChatMessage) => void;
}

export interface UserBubbleActions {
  /** Absent for stale archives whose backup was retired (fork would 404). */
  onFork?: (msg: PrepChatMessage) => void;
  onRetract?: (msg: PrepChatMessage) => void;
}

/** Memoized assistant bubble rendering streamed answer and trace. */
export const AssistantBubble = memo(function AssistantBubble({
  msg,
  actions,
}: {
  msg: PrepChatMessage;
  actions?: AssistantBubbleActions;
}) {
  const t = useT("prep");
  // Width grows with streamed content up to the bubble cap, then locks:
  // expanding/collapsing the timeline must not resize the bubble.
  const { ref: widthRef, minWidth } = useMonotonicWidth<HTMLDivElement>();
  return (
    <div className="flex gap-2.5">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--info-soft)] text-[var(--info-ink)]">
        <Bot size={14} />
      </span>
      <div
        ref={widthRef}
        style={minWidth === undefined ? undefined : { minWidth }}
        className="min-w-0 w-fit max-w-[88%] rounded-md rounded-bl-sm border border-surface-border bg-surface-alt px-3.5 py-2.5 text-[13px] leading-relaxed text-ink"
      >
        <div className="space-y-2">
          {msg.streaming && msg.statusText ? (
            <p className="flex items-center gap-1.5 text-[11px] text-ink-muted">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--primary)]" />
              {msg.statusText}
            </p>
          ) : null}
          {msg.trace && msg.trace.length > 0 ? (
            <TraceTimeline trace={msg.trace} streaming={!!msg.streaming} />
          ) : null}
          {msg.searchGroups && msg.searchGroups.length > 0 ? (
            <SearchResultCards groups={msg.searchGroups} />
          ) : null}
          <ThinkAnswerMessage content={msg.content} streaming={!!msg.streaming} />
          {!msg.content && msg.stopped && !msg.streaming ? (
            <p className="flex items-center gap-1.5 text-[11px] text-ink-subtle">
              <OctagonX size={12} />
              {t("chat.stoppedEmpty")}
            </p>
          ) : null}
          {msg.stopped && !msg.streaming && msg.content ? (
            <p className="flex items-center gap-1.5 text-[11px] text-ink-subtle">
              <OctagonX size={12} />
              {t("chat.stopped")}
            </p>
          ) : null}
        </div>
        {actions && msg.backendIndex !== undefined ? (
          <AssistantMessageActions
            content={msg.content}
            onExport={() => actions.onExport(msg)}
            onFork={actions.onFork ? () => actions.onFork?.(msg) : undefined}
            onRegenerate={actions.onRegenerate ? () => actions.onRegenerate?.(msg) : undefined}
            onRate={actions.onRate ? () => actions.onRate?.(msg) : undefined}
          />
        ) : null}
      </div>
    </div>
  );
});

/** Plain user message bubble with copy/fork/retract actions. */
export function UserBubble({
  msg,
  actions,
}: {
  msg: PrepChatMessage;
  actions?: UserBubbleActions;
}) {
  return (
    <div className="flex flex-row-reverse gap-2.5">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--primary)] text-white">
        <User size={14} />
      </span>
      <div className="min-w-0 max-w-[88%]">
        <div className="rounded-md rounded-br-sm bg-[var(--primary)] px-3.5 py-2.5 text-[13px] leading-relaxed text-white">
          <MarkdownContent content={msg.content} className="markdown-user" />
        </div>
        {actions && msg.backendIndex !== undefined ? (
          <UserMessageActions
            content={msg.content}
            onFork={actions.onFork ? () => actions.onFork?.(msg) : undefined}
            onRetract={actions.onRetract ? () => actions.onRetract?.(msg) : undefined}
          />
        ) : null}
      </div>
    </div>
  );
}
