"use client";

/**
 * @file ThinkAnswerMessage.tsx
 * @description Answer-only message body: strips internal thinking blocks and
 * tool-call JSON from the content, then streams the visible answer.
 * Thinking/tool progress renders separately in TraceTimeline.
 */

import { memo, useMemo } from "react";
import { StreamingReveal } from "@/components/StreamingReveal";
import { splitThinkAnswer, stripToolCallJson } from "@/lib/thinkStream";
import { cn } from "@/lib/utils";

interface ThinkAnswerMessageProps {
  content: string;
  streaming?: boolean;
  className?: string;
}

export const ThinkAnswerMessage = memo(function ThinkAnswerMessage({
  content,
  streaming = false,
  className,
}: ThinkAnswerMessageProps) {
  const answer = useMemo(() => {
    const split = splitThinkAnswer(content);
    return stripToolCallJson(split.answer);
  }, [content]);

  if (!answer) return null;
  return (
    <div className={cn("min-w-0", className)}>
      <StreamingReveal content={answer} streaming={streaming} />
    </div>
  );
});
