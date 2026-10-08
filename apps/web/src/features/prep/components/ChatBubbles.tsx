/**
 * @file ChatBubbles.tsx
 * @description Prep chat bubbles: assistant (status, trace timeline, search
 * cards, answer, stopped badge, action bar) and user (content, action bar).
 */

import { memo } from "react";
import { Bot, OctagonX } from "lucide-react";
import { useT } from "@/i18n";
import { MarkdownContent } from "@/components/MarkdownContent";
import type { PrepChatMessage } from "../types";
import { useMonotonicWidth } from "../hooks/useMonotonicWidth";
import { AskViewCard } from "./AskViewCard";
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

/** Streaming status line shown above the answer while tokens arrive. */
const StreamingStatus = ({ text }: { text: string }) => (
  <p className="flex items-center gap-1.5 text-[11px] text-ink-muted">
    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--primary)]" />
    {text}
  </p>
);

/** Stopped badge: a different label when the stream ended without an answer. */
const StoppedBadge = ({ empty }: { empty: boolean }) => {
  const t = useT("prep");
  return (
    <p className="flex items-center gap-1.5 text-[11px] text-ink-subtle">
      <OctagonX size={12} />
      {empty ? t("chat.stoppedEmpty") : t("chat.stopped")}
    </p>
  );
};

/** Search result cards, rendered only when the message carries groups. */
const MessageSearchCards = ({ groups }: { groups?: PrepChatMessage["searchGroups"] }) => {
  if (!groups || groups.length === 0) return null;
  return <SearchResultCards groups={groups} />;
};

/** Memoized assistant bubble rendering streamed answer and trace. */
export const AssistantBubble = memo(function AssistantBubble({
  msg,
  actions,
}: {
  msg: PrepChatMessage;
  actions?: AssistantBubbleActions;
}) {
  // Width grows with streamed content up to the bubble cap, then locks:
  // expanding/collapsing the timeline must not resize the bubble.
  const { ref: widthRef, minWidth } = useMonotonicWidth<HTMLDivElement>();
  // A trace timeline needs the full bubble width — hugging content (w-fit)
  // left the panel narrow with dead space to the right. Plain text replies
  // keep the hugging fit.
  const hasTrace = !!msg.trace && msg.trace.length > 0;
  const stopped = msg.stopped && !msg.streaming;
  return (
    <div className="flex gap-2.5">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--info-soft)] text-[var(--info-ink)]">
        <Bot size={14} />
      </span>
      <div
        ref={widthRef}
        style={minWidth === undefined ? undefined : { minWidth }}
        className={`min-w-0 max-w-[88%] rounded-md rounded-bl-sm border border-surface-border bg-surface-alt px-3.5 py-2.5 text-[13px] leading-relaxed text-ink ${hasTrace ? "w-full" : "w-fit"}`}
      >
        <div className="space-y-2">
          {msg.streaming && msg.statusText ? <StreamingStatus text={msg.statusText} /> : null}
          {hasTrace && msg.trace ? (
            <TraceTimeline trace={msg.trace} streaming={!!msg.streaming} />
          ) : null}
          <MessageSearchCards groups={msg.searchGroups} />
          {msg.ask ? <AskViewCard ask={msg.ask} /> : null}
          <ThinkAnswerMessage content={msg.content} streaming={!!msg.streaming} />
          {stopped ? <StoppedBadge empty={!msg.content} /> : null}
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

/** Plain user message bubble with copy/fork/retract actions (no avatar row). */
export const UserBubble = ({
  msg,
  actions,
}: {
  msg: PrepChatMessage;
  actions?: UserBubbleActions;
}) => {
  return (
    <div className="flex flex-row-reverse">
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
};
