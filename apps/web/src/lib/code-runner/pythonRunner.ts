/**
 * @file pythonRunner.ts
 * @description Python snippet execution via skulpt (in-browser interpreter).
 * skulpt ships only as classic scripts, so the engine loads from the vendored
 * copies under public/vendor/skulpt (pinned skulpt 1.2.0, no CDN, no CSP
 * change, works offline). Runs are serialized because Sk.configure targets
 * global state; CPU abuse is bounded by execLimit (raises TimeLimitError).
 * Subset limits (no third-party packages, no file/network access) are
 * inherent to skulpt and surface as ordinary runtime errors.
 */

import { truncateText } from "./output";
import {
  DEFAULT_MAX_OUTPUT_CHARS,
  DEFAULT_TIMEOUT_MS,
  type ExecutionHandle,
  type ExecutionResult,
} from "./types";

/** Minimal skulpt surface used here (full @types/skulpt is script-tag-hostile). */
interface SkulptGlobal {
  configure(options: {
    output: (text: string) => void;
    read: (filename: string) => string;
    execLimit?: number;
    __future__?: unknown;
  }): void;
  misceval: {
    asyncToPromise(fn: () => unknown): Promise<unknown>;
  };
  importMainWithBody(
    name: string,
    dumpJs: boolean,
    code: string,
    canSuspend: boolean,
  ): unknown;
  builtinFiles: { files: Record<string, string> };
  python3?: unknown;
}

declare global {
  interface Window {
    Sk?: SkulptGlobal;
  }
}

const VENDOR_BASE = "/vendor/skulpt";
const SCRIPT_LOAD_TIMEOUT_MS = 30000;

/** Cached engine promise: concurrent callers share one load. */
let enginePromise: Promise<SkulptGlobal> | null = null;

/** Serialized tail: skulpt output capture is global, so runs queue up. */
let runTail: Promise<unknown> = Promise.resolve();

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (typeof document === "undefined") {
      reject(new Error("No document available for script loading."));
      return;
    }
    if (document.querySelector(`script[data-skulpt="${src}"]`)) {
      resolve();
      return;
    }
    const el = document.createElement("script");
    el.src = src;
    el.async = false;
    el.dataset.skulpt = src;
    const timer = window.setTimeout(() => {
      el.remove();
      reject(new Error(`Timed out loading ${src}.`));
    }, SCRIPT_LOAD_TIMEOUT_MS);
    el.onload = () => {
      window.clearTimeout(timer);
      resolve();
    };
    el.onerror = () => {
      window.clearTimeout(timer);
      el.remove();
      reject(new Error(`Failed to load ${src}.`));
    };
    document.head.appendChild(el);
  });
}

/** Load the vendored skulpt engine once; rejects when unavailable. */
function loadSkulpt(): Promise<SkulptGlobal> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Python execution needs a browser."));
  }
  const preloaded = window.Sk;
  if (
    preloaded?.misceval &&
    typeof preloaded.importMainWithBody === "function"
  ) {
    return Promise.resolve(preloaded);
  }
  if (!enginePromise) {
    enginePromise = (async () => {
      await loadScript(`${VENDOR_BASE}/skulpt.min.js`);
      await loadScript(`${VENDOR_BASE}/skulpt-stdlib.js`);
      const engine = window.Sk;
      if (!engine?.misceval || !engine?.importMainWithBody) {
        throw new Error("Skulpt engine failed to initialize.");
      }
      return engine;
    })().catch((err: unknown) => {
      // Allow a later retry after transient failures.
      enginePromise = null;
      throw err;
    });
  }
  return enginePromise;
}

/** Best-effort "Type: detail" from the many shapes skulpt errors take. */
export function formatSkulptError(err: unknown): string {
  if (err === null || err === undefined) return "Unknown error";
  try {
    const record = err as {
      tp$name?: unknown;
      args?: { v?: { v?: unknown }[] };
      message?: unknown;
    };
    const name =
      typeof record.tp$name === "string" && record.tp$name
        ? record.tp$name
        : err instanceof Error
          ? err.name
          : "Error";
    const firstArg = record.args?.v?.[0]?.v;
    const detail =
      typeof firstArg === "string" && firstArg
        ? firstArg
        : typeof record.message === "string" && record.message
          ? record.message
          : "";
    return detail ? `${name}: ${detail}` : name;
  } catch {
    return "Unknown error";
  }
}

/** Execute Python source with the vendored skulpt engine. SSR-safe. */
export function runPython(
  source: string,
  limits?: { timeoutMs?: number; maxOutputChars?: number },
): ExecutionHandle {
  const timeoutMs = Math.max(1000, limits?.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const maxChars = limits?.maxOutputChars ?? DEFAULT_MAX_OUTPUT_CHARS;
  if (!source.trim()) {
    return {
      done: Promise.resolve({
        status: "ok",
        output: "",
        durationMs: 0,
        truncated: false,
      }),
      cancel() {},
    };
  }

  let cancelled = false;
  const startedAt = Date.now();
  const settleResult = (partial: {
    status: ExecutionResult["status"];
    output: string;
    error?: string;
  }): ExecutionResult => {
    const out = truncateText(partial.output, maxChars);
    return {
      status: cancelled && partial.status !== "unavailable" ? "cancelled" : partial.status,
      output: out.text,
      error:
        cancelled && partial.status !== "unavailable"
          ? "Execution cancelled."
          : partial.error,
      durationMs: Date.now() - startedAt,
      truncated: out.truncated,
    };
  };

  const run = (async (): Promise<ExecutionResult> => {
    // Serialize against earlier runs: Sk.configure output capture is global.
    await runTail.catch(() => {});
    if (cancelled) {
      return settleResult({ status: "cancelled", output: "" });
    }
    let engine: SkulptGlobal;
    try {
      engine = await loadSkulpt();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return settleResult({
        status: "unavailable",
        output: "",
        error: `Python runner unavailable: ${message}`,
      });
    }
    let captured = "";
    try {
      engine.configure({
        output: (text: string) => {
          captured += text;
          if (captured.length > maxChars + 1024) {
            // Stop feeding runaway prints; truncation is reported below.
            captured = captured.slice(0, maxChars + 1024);
          }
        },
        read: (filename: string) => {
          const files = engine.builtinFiles?.files;
          if (!files || !(filename in files)) {
            throw new Error(`Module not available in the browser sandbox: ${filename}`);
          }
          return files[filename] as string;
        },
        execLimit: timeoutMs,
        __future__: engine.python3,
      });
      await engine.misceval.asyncToPromise(() =>
        engine.importMainWithBody("<stdin>", false, source, true),
      );
      return settleResult({ status: "ok", output: captured });
    } catch (err) {
      const message = formatSkulptError(err);
      const timedOut =
        (err as { tp$name?: unknown })?.tp$name === "TimeLimitError" ||
        /timed out|TimeLimit/i.test(message);
      return settleResult({
        status: timedOut ? "timeout" : "error",
        output: captured,
        error: timedOut ? `Execution timed out after ${timeoutMs} ms.` : message,
      });
    }
  })();
  runTail = run.catch(() => {});

  return {
    done: run,
    cancel() {
      // skulpt cannot be preempted mid-run; execLimit bounds the overrun and
      // the outcome is reported as cancelled once the engine settles.
      cancelled = true;
    },
  };
}
