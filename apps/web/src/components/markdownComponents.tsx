"use client";

import { Children, type ReactNode } from "react";
import type { Components } from "react-markdown";
import { CodeBlock } from "./CodeBlock";
import { MermaidBlock } from "./MermaidBlock";
import { safeHttpUrl } from "./markdownSafeUrl";

/** Flatten code children to raw text (react-markdown passes strings). */
function codeText(children: ReactNode): string {
  return Children.toArray(children)
    .map((c) => (typeof c === "string" ? c : ""))
    .join("");
}

/** Language tag from a `language-*` class (undefined for plain fences). */
function codeLanguage(className?: string): string | undefined {
  const match = /language-([\w+-]+)/.exec(className ?? "");
  return match?.[1]?.toLowerCase();
}

/** react-markdown component map: styles and link safety live here, decoupled from the render entry. */
export const markdownComponents: Components = {
  h1: ({ children }) => (
    <h1 className="mt-3 mb-1.5 text-base font-bold tracking-tight first:mt-0 text-ink">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mt-3 mb-1.5 text-base font-bold tracking-tight first:mt-0 text-ink">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mt-2.5 mb-1 text-[14px] font-semibold first:mt-0 text-ink">{children}</h3>
  ),
  p: ({ children }) => <p className="mb-2 leading-relaxed text-ink last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5 text-ink">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5 text-ink">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => (
    <strong className="font-semibold text-ink">{children}</strong>
  ),
  em: ({ children }) => <em className="italic">{children}</em>,
  code: ({ className, children }) => {
    const language = codeLanguage(className);
    const text = codeText(children);
    // Mermaid fences render as diagrams once they parse; partial streams and
    // invalid charts fall back to source inside MermaidBlock.
    if (language === "mermaid") {
      return <MermaidBlock chart={text.trim()} />;
    }
    if (language) {
      return <CodeBlock language={language} text={text.replace(/\n$/, "")} />;
    }
    // Plain fenced blocks (no language, multiline) get the same chrome as
    // coded fences — header with plain-text label plus copy button — instead
    // of collapsing into an inline-code pill that loses line breaks.
    if (text.includes("\n")) {
      return <CodeBlock text={text.replace(/\n$/, "")} />;
    }
    return (
      <code className="rounded border border-surface-border bg-surface-muted px-1 py-0.5 font-mono text-[0.85em] text-ink">
        {children}
      </code>
    );
  },
  // Blocks bring their own chrome (CodeBlock/MermaidBlock); keep pre neutral.
  pre: ({ children }) => <div className="my-2 min-w-0">{children}</div>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-[var(--primary)] pl-3 italic text-ink-muted">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-3 border-surface-border" />,
  a: ({ href, children }) => {
    const safe = safeHttpUrl(href);
    if (!safe) {
      return <span className="text-[var(--primary)]">{children}</span>;
    }
    return (
      <a
        href={safe}
        className="text-[var(--primary)] underline underline-offset-2 hover:no-underline"
        target="_blank"
        rel="noopener noreferrer"
      >
        {children}
      </a>
    );
  },
  // GFM Form #:
  table: ({ children }) => (
    <div className="my-3 w-full max-w-full overflow-x-auto rounded-md border border-surface-border">
      <table className="w-full min-w-[320px] border-collapse text-left text-[13px] tabular-nums">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => (
    // Header uses the muted surface (not background-alt): on the near-white
    // message bubble the old fill was invisible, so the header read as a
    // plain body row.
    <thead className="bg-surface-muted text-ink">{children}</thead>
  ),
  tbody: ({ children }) => <tbody className="divide-y divide-surface-border">{children}</tbody>,
  tr: ({ children }) => (
    <tr className="border-b border-surface-border last:border-0 even:bg-surface-alt hover:bg-surface-muted">
      {children}
    </tr>
  ),
  th: ({ children }) => (
    <th className="border-b border-surface-border px-3 py-2 align-top text-[12px] font-semibold tracking-[0.02em] whitespace-nowrap text-ink">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="min-w-0 px-3 py-2 align-top leading-relaxed text-ink-muted [overflow-wrap:anywhere]">
      {children}
    </td>
  ),
};
