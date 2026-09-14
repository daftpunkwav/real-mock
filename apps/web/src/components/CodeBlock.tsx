/**
 * @file CodeBlock.tsx
 * @description Fenced code block chrome: language label, copy button,
 * optional run button (python / javascript / typescript only — other
 * languages are copy-only), and an execution output panel. Syntax
 * highlighting and execution engines load on demand; this module only
 * orchestrates them through the code-runner registry.
 */

import dynamic from "next/dynamic";
import { memo, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Check, Copy, Play, Square, X } from "lucide-react";
import { useT } from "@/i18n";
import { copyTextToClipboard } from "@/lib/clipboard";
import {
  getRunner,
  isRunnable,
  type ExecutionHandle,
  type ExecutionResult,
} from "@/lib/code-runner";

/** Feedback duration for the copied state. */
const COPIED_RESET_MS = 1500;

/** Highlighter chunk loads lazily; plain text shows meanwhile. */
const LazyHighlight = dynamic(
  () => import("./SyntaxHighlight").then((m) => m.SyntaxHighlight),
  { ssr: false, loading: () => null },
);

/** i18n key per execution status (explicit map keeps Translator typing exact). */
const STATUS_KEYS = {
  ok: "code.status.ok",
  error: "code.status.error",
  timeout: "code.status.timeout",
  cancelled: "code.status.cancelled",
  unavailable: "code.status.unavailable",
} as const;

function StatusPill({ result }: { result: ExecutionResult }) {
  const t = useT("common");
  const tone =
    result.status === "ok"
      ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
      : result.status === "timeout" || result.status === "error"
        ? "bg-red-500/15 text-red-600 dark:text-red-400"
        : "bg-surface-muted text-ink-subtle";
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${tone}`}
      role="status"
    >
      {t(STATUS_KEYS[result.status])} ·{" "}
      {t("code.durationMs", { ms: result.durationMs })}
    </span>
  );
}

export const CodeBlock = memo(function CodeBlock({
  language,
  text,
}: {
  language?: string;
  text: string;
}) {
  const t = useT("common");
  const [copied, setCopied] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ExecutionResult | null>(null);
  const runRef = useRef<{ generation: number; handle: ExecutionHandle | null }>({
    generation: 0,
    handle: null,
  });

  // A new snippet resets prior execution state; stale runs are ignored.
  useEffect(() => {
    runRef.current.generation += 1;
    try {
      runRef.current.handle?.cancel();
    } catch {
      /* already settled */
    }
    runRef.current.handle = null;
    setRunning(false);
    setResult(null);
  }, [text, language]);

  // Abort in-flight runs on unmount (frees workers, drops late results).
  useEffect(
    () => () => {
      runRef.current.generation += 1;
      try {
        runRef.current.handle?.cancel();
      } catch {
        /* already settled */
      }
    },
    [],
  );

  const onCopy = useCallback(() => {
    void copyTextToClipboard(text).then((ok) => {
      if (!ok) return;
      setCopied(true);
      window.setTimeout(() => setCopied(false), COPIED_RESET_MS);
    });
  }, [text]);

  const onRun = useCallback(() => {
    const runner = getRunner(language);
    if (!runner) return;
    const generation = runRef.current.generation + 1;
    runRef.current.generation = generation;
    try {
      runRef.current.handle?.cancel();
    } catch {
      /* already settled */
    }
    setResult(null);
    setRunning(true);
    const handle = runner.run(text);
    runRef.current.handle = handle;
    void handle.done.then((outcome) => {
      if (runRef.current.generation !== generation) return;
      runRef.current.handle = null;
      setRunning(false);
      setResult(outcome);
    });
  }, [language, text]);

  const onStop = useCallback(() => {
    try {
      runRef.current.handle?.cancel();
    } catch {
      /* already settled */
    }
  }, []);

  const runnable = isRunnable(language);

  return (
    <div className="my-2 overflow-hidden rounded-md border border-surface-border">
      <div className="flex items-center justify-between gap-2 border-b border-surface-border bg-surface-muted px-3 py-1.5">
        <span className="truncate font-mono text-[11px] text-ink-subtle">
          {language || t("code.plain")}
        </span>
        <div className="flex shrink-0 items-center gap-1">
          {runnable && !running && (
            <button
              type="button"
              onClick={onRun}
              className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-ink-subtle transition-colors hover:bg-surface-alt hover:text-ink"
              aria-label={t("code.run")}
            >
              <Play size={12} />
              {t("code.run")}
            </button>
          )}
          {runnable && running && (
            <button
              type="button"
              onClick={onStop}
              className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-ink-subtle transition-colors hover:bg-surface-alt hover:text-ink"
              aria-label={t("code.stop")}
            >
              <Square size={12} />
              {t("code.stop")}
            </button>
          )}
          <button
            type="button"
            onClick={onCopy}
            className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-ink-subtle transition-colors hover:bg-surface-alt hover:text-ink"
            aria-label={copied ? t("code.copied") : t("code.copy")}
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            {copied ? t("code.copied") : t("code.copy")}
          </button>
        </div>
      </div>
      <pre className="overflow-x-auto bg-surface-alt p-3">
        <code className="block font-mono text-xs leading-relaxed whitespace-pre-wrap text-ink">
          <Suspense fallback={text}>
            <LazyHighlight code={text} language={language} />
          </Suspense>
        </code>
      </pre>
      {(running || result) && (
        <div className="border-t border-surface-border bg-surface-muted">
          <div className="flex items-center justify-between gap-2 px-3 py-1.5">
            <div className="flex min-w-0 items-center gap-2">
              <span className="shrink-0 font-mono text-[11px] text-ink-subtle">
                {t("code.output")}
              </span>
              {running && (
                <span
                  className="rounded-full bg-surface-alt px-2 py-0.5 text-[11px] text-ink-subtle"
                  role="status"
                >
                  {t("code.running")}
                </span>
              )}
              {result && <StatusPill result={result} />}
            </div>
            {!running && result && (
              <button
                type="button"
                onClick={() => setResult(null)}
                className="flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-ink-subtle transition-colors hover:bg-surface-alt hover:text-ink"
                aria-label={t("code.closeOutput")}
              >
                <X size={12} />
              </button>
            )}
          </div>
          {result && (result.output || result.stderr || result.error) && (
            <div className="space-y-1 px-3 pb-3">
              {result.output && (
                <pre className="overflow-x-auto rounded bg-surface-alt p-2.5">
                  <code className="block font-mono text-xs leading-relaxed whitespace-pre-wrap text-ink">
                    {result.output}
                  </code>
                </pre>
              )}
              {result.stderr && (
                <pre className="overflow-x-auto rounded bg-surface-alt p-2.5">
                  <code className="block font-mono text-xs leading-relaxed whitespace-pre-wrap text-amber-600 dark:text-amber-400">
                    {result.stderr}
                  </code>
                </pre>
              )}
              {result.error && (
                <pre className="overflow-x-auto rounded bg-red-500/10 p-2.5">
                  <code className="block font-mono text-xs leading-relaxed whitespace-pre-wrap text-red-600 dark:text-red-400">
                    {result.error}
                  </code>
                </pre>
              )}
              {result.truncated && (
                <p className="text-[11px] text-ink-subtle">{t("code.truncated")}</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
});
