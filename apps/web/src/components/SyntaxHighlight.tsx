/**
 * @file SyntaxHighlight.tsx
 * @description Prism-based syntax highlighting for fenced code, loaded on
 * demand (the parent lazy-loads this module so the highlighter never lands in
 * the main bundle). Unknown languages and oversized inputs fall back to plain
 * text. Prism escapes source HTML during tokenization, so injecting the
 * highlighted markup is safe.
 */

import { memo, useMemo } from "react";
import Prism from "prismjs";
// Dependency order matters: extensions build on the grammars above them.
import "prismjs/components/prism-markup";
import "prismjs/components/prism-css";
import "prismjs/components/prism-clike";
import "prismjs/components/prism-javascript";
import "prismjs/components/prism-typescript";
import "prismjs/components/prism-jsx";
import "prismjs/components/prism-tsx";
import "prismjs/components/prism-python";
import "prismjs/components/prism-json";
import "prismjs/components/prism-bash";
import "prismjs/components/prism-yaml";
import "prismjs/components/prism-markdown";
import "prismjs/components/prism-sql";
import "prismjs/components/prism-java";
import "prismjs/components/prism-c";
import "prismjs/components/prism-cpp";
import "prismjs/components/prism-csharp";
import "prismjs/components/prism-go";
import "prismjs/components/prism-rust";
import "prismjs/components/prism-diff";
import styles from "./SyntaxHighlight.module.css";

/** Fence id aliases that differ from Prism grammar names. */
const LANGUAGE_ALIASES: Record<string, string> = {
  html: "markup",
  xml: "markup",
  svg: "markup",
  js: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  ts: "typescript",
  mts: "typescript",
  py: "python",
  sh: "bash",
  shell: "bash",
  zsh: "bash",
  yml: "yaml",
  md: "markdown",
  h: "cpp",
  "c++": "cpp",
  "c#": "csharp",
};

/** Above this size highlighting would block the UI; render plain text. */
const HIGHLIGHT_CHAR_BUDGET = 120_000;

export const SyntaxHighlight = memo(function SyntaxHighlight({
  code,
  language,
}: {
  code: string;
  language?: string;
}) {
  const html = useMemo(() => {
    if (!code || code.length > HIGHLIGHT_CHAR_BUDGET) return null;
    const raw = (language ?? "").trim().toLowerCase();
    const grammarId = LANGUAGE_ALIASES[raw] ?? raw;
    if (!grammarId) return null;
    const grammar = (Prism.languages as Record<string, unknown>)[grammarId];
    if (!grammar) return null;
    try {
      return Prism.highlight(
        code,
        grammar as Parameters<typeof Prism.highlight>[1],
        grammarId,
      );
    } catch {
      // A broken grammar must never break the message render.
      return null;
    }
  }, [code, language]);

  if (html === null) return <>{code}</>;
  return (
    <span className={styles.code} dangerouslySetInnerHTML={{ __html: html }} />
  );
});
