import type { ChatMessage } from "@/lib/api/contract";

/** Keep only visible user and assistant messages with content. */
export function toVisibleChatMessages(raw: ChatMessage[]): ChatMessage[] {
  return raw.filter(
    (m) => (m.role === "user" || m.role === "assistant") && Boolean(m.content?.trim()),
  );
}

function sameTurn(a: ChatMessage | undefined, b: ChatMessage | undefined): boolean {
  if (!a || !b) return false;
  return a.role === b.role && a.content === b.content;
}

/** True when every turn in ``head`` matches the start of ``full``. */
function isPrefix(head: ChatMessage[], full: ChatMessage[]): boolean {
  if (head.length > full.length) return false;
  for (let i = 0; i < head.length; i += 1) {
    if (!sameTurn(head[i], full[i])) return false;
  }
  return true;
}

/** Longest suffix of ``history`` that equals a prefix of ``live``. */
function overlapCount(history: ChatMessage[], live: ChatMessage[]): number {
  const max = Math.min(history.length, live.length);
  let best = 0;
  for (let k = 1; k <= max; k += 1) {
    let matches = true;
    for (let i = 0; i < k; i += 1) {
      if (!sameTurn(history[history.length - k + i], live[i])) {
        matches = false;
        break;
      }
    }
    if (matches) best = k;
  }
  return best;
}

/**
 * Apply a history snapshot without dropping turns that already arrived on the
 * socket, and without repeating a turn that is still streaming.
 */
export function mergeRestoredMessages(
  history: ChatMessage[],
  live: ChatMessage[],
  streamingText = "",
): ChatMessage[] {
  let restored = history;
  const partial = streamingText.trim();
  if (partial && restored.length > 0) {
    const last = restored[restored.length - 1];
    if (last && last.role === "assistant" && last.content.startsWith(partial)) {
      restored = restored.slice(0, -1);
    }
  }
  if (live.length === 0) return restored;
  // Live is the head of a longer snapshot: the snapshot already contains it.
  if (isPrefix(live, restored)) return restored;
  // Snapshot is the head of live turns that continued after it was taken.
  if (isPrefix(restored, live)) return live;
  const overlap = overlapCount(restored, live);
  return [...restored.slice(0, restored.length - overlap), ...live];
}
