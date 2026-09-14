/**
 * @file typescriptRunner.ts
 * @description TypeScript snippet execution: strip types with sucrase
 * (bundled, loaded on demand — no network, no CSP change), then delegate to
 * the JavaScript worker runner. Transpile failures surface as error results
 * without ever spawning a worker.
 *
 * The worker runs snippets via `new Function`, which rejects module syntax,
 * so the sucrase "imports" transform lowers `import`/`export` to CJS. The
 * worker provides minimal `module`/`exports` shims for those; real `require`
 * calls fail with a guidance error (no module loader in the browser).
 */

import { runJavascript } from "./javascriptRunner";
import type { ExecutionHandle } from "./types";

/** Transpile outcome: runnable code or a human-readable diagnostic. */
export type TranspileOutcome = { code: string } | { error: string };

/**
 * Strip TypeScript syntax via sucrase. Pure async (dynamic import keeps the
 * transpiler out of the main bundle); safe to call in Node for tests.
 */
export async function transpileTypeScript(
  source: string,
  jsx = false,
): Promise<TranspileOutcome> {
  if (!source.trim()) return { code: "" };
  try {
    const { transform } = await import("sucrase");
    const transforms = jsx ? ["typescript", "jsx", "imports"] : ["typescript", "imports"];
    const { code } = transform(source, {
      transforms: transforms as ("typescript" | "jsx" | "imports")[],
    });
    return { code };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { error: `TypeScript parse failed: ${message}` };
  }
}

/** Execute TypeScript source (optionally with JSX) via the JS worker. */
export function runTypeScript(
  source: string,
  limits?: { timeoutMs?: number; maxOutputChars?: number },
  jsx = false,
): ExecutionHandle {
  let cancelled = false;
  let inner: ExecutionHandle | null = null;
  const done = (async () => {
    const outcome = await transpileTypeScript(source, jsx);
    if (cancelled) {
      return {
        status: "cancelled" as const,
        output: "",
        error: "Execution cancelled.",
        durationMs: 0,
        truncated: false,
      };
    }
    if ("error" in outcome) {
      return {
        status: "error" as const,
        output: "",
        error: outcome.error,
        durationMs: 0,
        truncated: false,
      };
    }
    inner = runJavascript(outcome.code, limits);
    return inner.done;
  })();
  return {
    done,
    cancel() {
      cancelled = true;
      inner?.cancel();
    },
  };
}
