/** Streaming SSE parser: line-oriented ``data: `` payloads; skip malformed lines. */

import { ApiError } from "./apiError";

interface SSERawEvent {
  type?: unknown;
  content?: unknown;
  token_usage?: unknown;
  message?: unknown;
  report?: unknown;
}

function isSsePayload(value: unknown): value is SSERawEvent {
  return typeof value === "object" && value !== null;
}

function dispatchSseLine<TEvent extends { type: string }>(
  line: string,
  onEvent: (event: TEvent) => void,
): void {
  const trimmed = line.trim();
  if (!trimmed.startsWith("data: ")) return;
  let payload: unknown;
  try {
    payload = JSON.parse(trimmed.slice(6));
  } catch {
    return; // skip bad lines instead of aborting the whole stream
  }
  if (!isSsePayload(payload)) return;
  onEvent(payload as TEvent);
}

/**
 * Consume an SSE Response; invoke ``onEvent``; throw ``ApiError`` on hard failures.
 *
 * ``onKeepAlive`` fires once per read that yields bytes (data lines, heartbeat
 * comments, separators alike), so callers can tell a live-but-quiet stream
 * apart from a half-open connection. It is optional; existing callers pass nothing.
 */
export async function consumeSSE<TEvent extends { type: string }>(
  res: Response,
  onEvent: (event: TEvent) => void,
  onKeepAlive?: () => void,
): Promise<void> {
  if (!res.body) throw new ApiError("Streaming response unavailable", res.status, { code: "NET0005" });

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        if (buffer.trim()) {
          for (const line of buffer.split("\n")) {
            dispatchSseLine(line, onEvent);
          }
        }
        break;
      }
      if (value && value.length > 0) onKeepAlive?.();
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        dispatchSseLine(line, onEvent);
      }
    }
  } finally {
    // cancel after a clean read is a no-op; on throw, release the reader lock / abort the stream
    reader.cancel().catch(() => {});
  }
}
