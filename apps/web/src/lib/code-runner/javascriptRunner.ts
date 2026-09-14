/**
 * @file javascriptRunner.ts
 * @description JavaScript snippet execution inside a Blob Web Worker.
 * The snippet runs off the UI thread with a captured console; a main-thread
 * timer terminates the worker on timeout. User source travels via postMessage
 * (never interpolated into the worker template), and the worker performs no
 * imports, so it cannot pull remote code. Residual risk: the worker shares the
 * page origin and could fetch same-origin URLs; treat snippets as
 * semi-trusted, same as pasting them into devtools.
 *
 * Module interop: snippets run inside `new Function`, so bare `import` /
 * `export` statements are syntax errors. The TypeScript runner lowers those
 * to CJS beforehand; the worker additionally provides minimal `module` /
 * `exports` shims plus a `require` that throws a guidance error. The
 * snippet is always the entry point, so `require.main === module` is true
 * and Node-idiom self-tests run their bodies instead of being skipped.
 */

import { formatLogArgs, truncateText } from "./output";
import {
  DEFAULT_MAX_OUTPUT_CHARS,
  DEFAULT_TIMEOUT_MS,
  type ExecutionHandle,
  type ExecutionResult,
} from "./types";

/**
 * Worker driver source. The serializer and error formatter are embedded from
 * the tested module functions (both kept self-contained precisely for this),
 * so worker-side formatting logic exists exactly once.
 * Exported for syntax-validation tests; not part of the public surface.
 */
export function buildWorkerSource(): string {
  return (
    "var formatLogArgs = " +
    formatLogArgs.toString() +
    ";\nvar formatWorkerError = " +
    // Declared below; hoisted, and self-contained like the serializer.
    formatWorkerError.toString() +
    ";\n" +
    "self.onmessage = async function (event) {\n" +
    "  var data = event.data || {};\n" +
    "  var source = typeof data.source === 'string' ? data.source : '';\n" +
    "  var stdout = [];\n" +
    "  var stderr = [];\n" +
    "  var sink = {};\n" +
    "  ['log', 'info', 'debug'].forEach(function (m) {\n" +
    "    sink[m] = function () { stdout.push(formatLogArgs(Array.prototype.slice.call(arguments))); };\n" +
    "  });\n" +
    "  ['warn', 'error'].forEach(function (m) {\n" +
    "    sink[m] = function () { stderr.push(formatLogArgs(Array.prototype.slice.call(arguments))); };\n" +
    "  });\n" +
    "  try {\n" +
    // Minimal CJS shims: sucrase-lowered `exports.*` assignments land here;
    // real require() calls fail loudly (no module loader in the browser).
    // `module.main === module` is true so the Node idiom
    // `if (require.main === module) { /* self-test */ }` runs its body —
    // the snippet is always the entry point here, never an import.
    "    var moduleShim = { exports: {} };\n" +
    "    moduleShim.main = moduleShim;\n" +
    "    var requireShim = function (name) { throw new Error(\"Cannot load module '\" + name + \"' in the browser runner. Only self-contained snippets can run here.\"); };\n" +
    "    requireShim.main = moduleShim;\n" +
    // Async wrapper: supports both sync snippets and top-level await.
    "    var fn = new Function('console', 'module', 'exports', 'require', '\"use strict\";\\nreturn (async function () {\\n' + source + '\\n})();');\n" +
    "    var returned = await fn(sink, moduleShim, moduleShim.exports, requireShim);\n" +
    "    if (returned !== undefined) stdout.push(formatLogArgs([returned]));\n" +
    "    self.postMessage({ ok: true, stdout: stdout.join('\\n'), stderr: stderr.join('\\n') });\n" +
    "  } catch (err) {\n" +
    "    self.postMessage({ ok: false, stdout: stdout.join('\\n'), stderr: stderr.join('\\n'), error: formatWorkerError(err) });\n" +
    "  }\n" +
    "};\n"
  );
}

/** Main-thread mirror of the worker error format (unit-testable).
 * Self-contained (no outer references): embedded into the worker as text. */
export function formatWorkerError(err: unknown): string {
  if (err === null || err === undefined) return "Unknown error";
  if (typeof err === "string") return err || "Unknown error";
  const record = err as { name?: unknown; message?: unknown; stack?: unknown };
  const name =
    typeof record.name === "string" && record.name ? record.name : "Error";
  let message = "";
  if (typeof record.message === "string" && record.message) {
    message = record.message;
  } else if (err instanceof Error) {
    message = err.message;
  } else {
    try {
      const fallback = String(err);
      message = fallback === "[object Object]" ? "" : fallback;
    } catch {
      message = "";
    }
  }
  let text = message ? `${name}: ${message}` : name;
  if (typeof record.stack === "string") {
    const frames = record.stack
      .split("\n")
      .slice(1, 4)
      .map((line) => line.replace(/blob:[^)\s]*/g, "blob:…").trim())
      .filter(Boolean);
    if (frames.length) text += `\n${frames.join("\n")}`;
  }
  return text;
}

/** Immediate handle for runs that never start (no Worker support, bad input). */
function immediate(result: Omit<ExecutionResult, "durationMs">): ExecutionHandle {
  return { done: Promise.resolve({ ...result, durationMs: 0 }), cancel() {} };
}

/** Execute JavaScript source in a sandboxed Blob worker. SSR-safe. */
export function runJavascript(
  source: string,
  limits?: { timeoutMs?: number; maxOutputChars?: number },
): ExecutionHandle {
  const timeoutMs = Math.max(1000, limits?.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const maxChars = limits?.maxOutputChars ?? DEFAULT_MAX_OUTPUT_CHARS;
  if (typeof Worker === "undefined" || typeof Blob === "undefined") {
    return immediate({
      status: "unavailable",
      output: "",
      error: "Code execution is not supported in this environment.",
      truncated: false,
    });
  }
  if (!source.trim()) {
    return immediate({ status: "ok", output: "", truncated: false });
  }

  let settle: ((result: ExecutionResult) => void) | null = null;
  const done = new Promise<ExecutionResult>((resolve) => {
    settle = resolve;
  });
  const startedAt = Date.now();
  let worker: Worker | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let url: string | null = null;
  let finished = false;

  const finish = (partial: Omit<ExecutionResult, "durationMs" | "truncated">) => {
    if (finished) return;
    finished = true;
    if (timer) clearTimeout(timer);
    try {
      worker?.terminate();
    } catch {
      /* already gone */
    }
    if (url) {
      try {
        URL.revokeObjectURL(url);
      } catch {
        /* ignore */
      }
    }
    worker = null;
    const out = truncateText(partial.output, maxChars);
    const err = partial.stderr ? truncateText(partial.stderr, maxChars) : null;
    settle?.({
      status: partial.status,
      output: out.text,
      stderr: err?.text || undefined,
      error: partial.error,
      durationMs: Date.now() - startedAt,
      truncated: out.truncated || Boolean(err?.truncated),
    });
  };

  try {
    const blob = new Blob([buildWorkerSource()], { type: "text/javascript" });
    url = URL.createObjectURL(blob);
    worker = new Worker(url);
  } catch (err) {
    return immediate({
      status: "unavailable",
      output: "",
      error: `Unable to start the execution worker: ${formatWorkerError(err)}`,
      truncated: false,
    });
  }

  timer = setTimeout(() => {
    finish({
      status: "timeout",
      output: "",
      error: `Execution timed out after ${timeoutMs} ms.`,
    });
  }, timeoutMs);

  worker.onmessage = (event: MessageEvent) => {
    const data = (event.data ?? {}) as {
      ok?: boolean;
      stdout?: string;
      stderr?: string;
      error?: string;
    };
    finish({
      status: data.ok ? "ok" : "error",
      output: typeof data.stdout === "string" ? data.stdout : "",
      stderr: typeof data.stderr === "string" && data.stderr ? data.stderr : undefined,
      error: data.ok ? undefined : data.error || "Execution failed.",
    });
  };
  worker.onerror = (event) => {
    finish({
      status: "error",
      output: "",
      error: `Worker error: ${event.message || "unknown"}`,
    });
  };
  worker.postMessage({ source });

  return {
    done,
    cancel() {
      finish({ status: "cancelled", output: "", error: "Execution cancelled." });
    },
  };
}
