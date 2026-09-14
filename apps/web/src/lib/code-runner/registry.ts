/**
 * @file registry.ts
 * @description Maps fence language ids to execution engines. UI code asks
 * isRunnable/getRunner only — engine modules stay behind this boundary, so
 * adding a language never touches rendering code.
 */

import { runJavascript } from "./javascriptRunner";
import { runPython } from "./pythonRunner";
import { runTypeScript } from "./typescriptRunner";
import type { CodeRunner, RunLimits } from "./types";

const javascriptRunner: CodeRunner = {
  id: "javascript",
  run: (source: string, limits?: RunLimits) => runJavascript(source, limits),
};

const typescriptRunner: CodeRunner = {
  id: "typescript",
  run: (source: string, limits?: RunLimits) => runTypeScript(source, limits),
};

const tsxRunner: CodeRunner = {
  id: "tsx",
  run: (source: string, limits?: RunLimits) => runTypeScript(source, limits, true),
};

const pythonRunner: CodeRunner = {
  id: "python",
  run: (source: string, limits?: RunLimits) => runPython(source, limits),
};

/** Canonical runner per language family (tsx needs the JSX transform). */
const RUNNERS: Record<string, CodeRunner> = {
  javascript: javascriptRunner,
  typescript: typescriptRunner,
  tsx: tsxRunner,
  python: pythonRunner,
};

/** Common fence aliases (```js / ```ts / ```py). */
const ALIASES: Record<string, string> = {
  js: "javascript",
  ts: "typescript",
  py: "python",
};

/** Normalize a fence language id for lookup (case/whitespace tolerant). */
export function normalizeLanguageId(language?: string): string {
  const id = (language ?? "").trim().toLowerCase();
  return ALIASES[id] ?? id;
}

/** True when the fence language can be executed in the browser. */
export function isRunnable(language?: string): boolean {
  return normalizeLanguageId(language) in RUNNERS;
}

/** Runner for a fence language, or undefined for copy-only languages. */
export function getRunner(language?: string): CodeRunner | undefined {
  return RUNNERS[normalizeLanguageId(language)];
}
