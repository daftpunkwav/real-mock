/**
 * @file slashCommands.ts
 * @description Prep composer slash commands: pure parsing/matching helpers.
 * Execution is split: usePrepChat dispatches (needs session state) and
 * usePrepCompact runs the HTTP call; this module stays UI-free and
 * unit-testable.
 */

/** Slash command names supported by the prep composer. */
export const SLASH_NAMES = ["compact", "clear", "help"] as const;

export type SlashName = (typeof SLASH_NAMES)[number];

/** Parse a leading "/" command; null when the input is not a slash command. */
export function parseSlashCommand(input: string): { name: string; args: string } | null {
  if (!input.startsWith("/")) return null;
  const body = input.slice(1).trim();
  if (!body) return { name: "", args: "" };
  const space = body.search(/\s/);
  if (space < 0) return { name: body.toLowerCase(), args: "" };
  return { name: body.slice(0, space).toLowerCase(), args: body.slice(space + 1).trim() };
}

/** Filter commands by the typed prefix (exact name matches first). */
export function matchSlashCommands(prefix: string): SlashName[] {
  const needle = prefix.toLowerCase();
  const hits = SLASH_NAMES.filter((name) => name.startsWith(needle));
  hits.sort((a, b) => {
    if (a === needle) return -1;
    if (b === needle) return 1;
    return a.localeCompare(b);
  });
  return hits;
}

/** Resolve an exact command name; null for unknown/empty names. */
export function resolveSlashCommand(name: string): SlashName | null {
  const needle = name.toLowerCase();
  return (SLASH_NAMES as readonly string[]).includes(needle) ? (needle as SlashName) : null;
}

/** Compression intensities accepted by /compact (English plus Chinese aliases). */
export const COMPACT_INTENSITY_ALIASES: Record<string, "light" | "balanced" | "aggressive"> = {
  light: "light",
  balanced: "balanced",
  aggressive: "aggressive",
  轻度: "light",
  标准: "balanced",
  中度: "balanced",
  重度: "aggressive",
};

/** Parsed /compact arguments: optional intensity plus a free-text directive. */
export interface CompactCommandArgs {
  intensity?: "light" | "balanced" | "aggressive";
  directive?: string;
}

/**
 * Parse "/compact [intensity] [directive...]": a leading intensity keyword
 * (or Chinese alias) selects the amplitude, everything else is the
 * compression directive. Unknown first words are treated as directive text,
 * never rejected.
 */
export function parseCompactArgs(args: string): CompactCommandArgs {
  const text = (args ?? "").trim();
  if (!text) return {};
  const space = text.search(/\s/);
  const head = (space < 0 ? text : text.slice(0, space)).toLowerCase();
  const intensity = COMPACT_INTENSITY_ALIASES[head];
  if (!intensity) return { directive: text };
  const rest = (space < 0 ? "" : text.slice(space + 1)).trim();
  return rest ? { intensity, directive: rest } : { intensity };
}
