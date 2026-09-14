"use client";

import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

/** Interview chat bubble: candidate / interviewer / legacy nudge styles. */
export function ChatBubble({
  role,
  content,
  streaming = false,
}: {
  role: string;
  content: string;
  streaming?: boolean;
}) {
  const t = useT("interview");
  const isUser = role === "user";
  // Legacy history may still carry a Chinese nudge prefix; new silence_nudge events do not
  const isNudge = content.startsWith("[追问]") || content.startsWith("[Follow-up]");

  return (
    <div className={cn("flex gap-2", isUser ? "flex-row-reverse" : "flex-row")}>
      <span
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-bold text-white",
          isUser
            ? "bg-[var(--primary)]"
            : "bg-[var(--info)] text-[var(--info-ink)]",
        )}
      >
        {isUser ? t("chat.bubble.me") : t("chat.bubble.ai")}
      </span>
      <div className={cn("flex max-w-[85%] flex-col", isUser ? "items-end" : "items-start")}>
        <span className="mb-0.5 px-0.5 text-[10px] text-ink-subtle">
          {isUser
            ? t("chat.bubble.candidate")
            : isNudge
              ? t("chat.bubble.interviewerNudge")
              : t("chat.bubble.interviewer")}
          {streaming && t("chat.bubble.streamingSuffix")}
        </span>
        <div
          className={cn(
            "rounded-md px-3 py-2 text-[13px] leading-relaxed",
            isUser
              ? "rounded-tr-sm bg-[var(--primary)] text-white"
              : isNudge
                ? "rounded-tl-sm border border-[var(--warning)]/30 bg-[var(--warning-soft)] text-[var(--warning-ink)]"
                : "rounded-tl-sm border border-surface-border bg-surface-alt text-ink",
          )}
        >
          {content}
          {streaming && (
            <span className="ml-0.5 inline-block h-3.5 w-1.5 anim-pulse-dot rounded-sm bg-[var(--primary)] align-middle" />
          )}
        </div>
      </div>
    </div>
  );
}
