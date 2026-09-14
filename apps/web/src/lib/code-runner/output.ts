/**
 * @file output.ts
 * @description Pure output helpers shared by runners: truncation and
 * JSON-safe formatting of console-style argument lists. No DOM, no Workers,
 * no engine imports — safe to unit test in Node.
 *
 * Implementation constraint: formatLogArgs must stay fully self-contained
 * (only locals plus JS globals). javascriptRunner embeds its source text into
 * the worker, so any outer-module reference would break at runtime.
 */

/** Cut text at a character cap; reports whether truncation happened. */
export function truncateText(
  text: string,
  maxChars: number,
): { text: string; truncated: boolean } {
  if (text.length <= maxChars) return { text, truncated: false };
  return { text: text.slice(0, maxChars), truncated: true };
}

/**
 * Format console-style arguments the way devtools print them: strings verbatim,
 * everything else JSON-ish, joined with a single space per call.
 * Never throws; unserializable values degrade to placeholders.
 */
export function formatLogArgs(args: readonly unknown[]): string {
  const formatOne = (value: unknown, depth: number): string => {
    if (typeof value === "string") return value;
    if (value === null || value === undefined) return String(value);
    const kind = typeof value;
    if (kind === "number" || kind === "boolean" || kind === "bigint") {
      return String(value);
    }
    if (kind === "function") {
      try {
        const name = (value as (...a: never[]) => unknown).name;
        return `[Function ${name || "anonymous"}]`;
      } catch {
        return "[Function]";
      }
    }
    if (depth <= 0) return Array.isArray(value) ? "[Array]" : "[Object]";
    if (value instanceof Error) return `${value.name}: ${value.message}`;
    try {
      const seen: unknown[] = [];
      const json = JSON.stringify(
        value,
        (_key: string, nested: unknown) => {
          if (nested !== null && typeof nested === "object") {
            if (seen.indexOf(nested) !== -1) return "[Circular]";
            seen.push(nested);
          }
          if (typeof nested === "bigint") return `${nested.toString()}n`;
          if (typeof nested === "function") return "[Function]";
          if (nested instanceof Error)
            return `${nested.name}: ${nested.message}`;
          return nested;
        },
        2,
      );
      return typeof json === "string" ? json : String(value);
    } catch {
      try {
        return String(value);
      } catch {
        return "[Unserializable]";
      }
    }
  };
  const parts: string[] = [];
  for (const arg of args) parts.push(formatOne(arg, 3));
  return parts.join(" ");
}
