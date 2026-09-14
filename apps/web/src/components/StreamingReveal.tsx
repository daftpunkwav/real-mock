"use client";

import { MarkdownContent } from "./MarkdownContent";

interface StreamingRevealProps {
  content: string;
  streaming: boolean;
}

/**
 * Render live-updating Markdown content; tolerant normalizer handles partial tables. Transport is caller-owned.
 */
export function StreamingReveal({ content, streaming }: StreamingRevealProps) {
  return (
    <div className="relative">
      <MarkdownContent
        content={content}
        className={streaming ? "markdown-streaming" : ""}
        final={!streaming}
      />
      {streaming && (
        <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-[var(--primary)] align-middle" />
      )}
    </div>
  );
}
