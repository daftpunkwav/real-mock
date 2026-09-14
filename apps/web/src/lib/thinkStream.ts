/**
 * Split streaming content into thinking vs final answer.
 *
 * Supports:
 * - ``<think>...</think>`` (some domestic models)
 * - ``<thinking>...</thinking>``
 * - ``\`\`\`thinking ... \`\`\``
 *
 * Tags may be split across tokens in streaming, so a ``pending`` buffer is kept.
 */

interface ThinkSplit {
  /** Closed or in-progress thinking body */
  thinking: string;
  /** Final answer (without thinking tags) */
  answer: string;
  /** Still inside a thinking block */
  inThinking: boolean;
  /** Whether a thinking block has appeared (controls fold UI) */
  hasThinking: boolean;
}

const OPEN_TAGS = ["<think>", "<thinking>", "```thinking"] as const;
const CLOSE_TAGS = ["</think>", "</thinking>", "```"] as const;

/** Whether s[i:] starts with an open tag (case-insensitive) */
function matchOpen(s: string, i: number): { tag: string; len: number } | null {
  const slice = s.slice(i);
  const lower = slice.toLowerCase();
  for (const tag of OPEN_TAGS) {
    if (lower.startsWith(tag.toLowerCase())) {
      // Allow a newline after ```thinking
      if (tag === "```thinking") {
        let len = tag.length;
        if (slice[len] === "\n" || slice[len] === "\r") {
          len += slice[len] === "\r" && slice[len + 1] === "\n" ? 2 : 1;
        }
        return { tag, len };
      }
      return { tag, len: tag.length };
    }
  }
  return null;
}

function matchClose(s: string, i: number, openTag: string | null): { len: number } | null {
  const slice = s.slice(i);
  const lower = slice.toLowerCase();
  if (openTag === "```thinking") {
    // Fenced-block close: a lone ```
    if (lower.startsWith("```") && (slice.length === 3 || /[\r\n]/.test(slice[3] ?? "\n") || slice[3] === undefined)) {
      return { len: 3 };
    }
    return null;
  }
  for (const tag of CLOSE_TAGS) {
    if (tag === "```") continue;
    if (lower.startsWith(tag.toLowerCase())) {
      return { len: tag.length };
    }
  }
  return null;
}

/**
 * Split the accumulated raw stream into thinking / answer.
 * Re-parse whenever content grows (O(n); fine for prep reply sizes).
 */
export function splitThinkAnswer(raw: string): ThinkSplit {
  let thinking = "";
  let answer = "";
  let inThinking = false;
  let hasThinking = false;
  let openTag: string | null = null;
  let i = 0;

  while (i < raw.length) {
    if (!inThinking) {
      const open = matchOpen(raw, i);
      if (open) {
        inThinking = true;
        hasThinking = true;
        openTag = open.tag;
        i += open.len;
        continue;
      }
      // Incomplete open-tag prefix — leave remainder pending if it looks like a tag start
      const rest = raw.slice(i);
      if (couldBeTagPrefix(rest, "open")) {
        break;
      }
      answer += raw[i];
      i += 1;
    } else {
      const close = matchClose(raw, i, openTag);
      if (close) {
        inThinking = false;
        openTag = null;
        i += close.len;
        continue;
      }
      const rest = raw.slice(i);
      if (couldBeTagPrefix(rest, "close", openTag)) {
        break;
      }
      thinking += raw[i];
      i += 1;
    }
  }

  return { thinking: thinking.trim(), answer: answer.trimStart(), inThinking, hasThinking };
}

function couldBeTagPrefix(
  rest: string,
  kind: "open" | "close",
  openTag?: string | null,
): boolean {
  if (!rest || rest.length > 20) return false;
  const lower = rest.toLowerCase();
  if (kind === "open") {
    return OPEN_TAGS.some((t) => t.toLowerCase().startsWith(lower) || lower.startsWith("<") || lower.startsWith("`"));
  }
  if (openTag === "```thinking") {
    return "`".startsWith(lower) || lower.startsWith("`");
  }
  return CLOSE_TAGS.some((t) => t !== "```" && (t.toLowerCase().startsWith(lower) || lower.startsWith("<")));
}

/** Drop thinking blocks; keep the final answer (persist/display fallback) */
export function stripThinking(raw: string): string {
  return splitThinkAnswer(raw).answer;
}

/** Strip ReAct tool-call JSON (frontend fallback so protocol does not leak into bubbles) */
const TOOL_JSON_RE = /\{[^{}]*["']tool["']\s*:\s*["']\w+["'][^{}]*\}/gi;

export function stripToolCallJson(text: string): string {
  if (!text) return text;
  return text
    .replace(TOOL_JSON_RE, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
