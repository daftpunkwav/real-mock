import type { ChatMessage } from "@/lib/api/contract";

/** Keep only visible user and assistant messages with content. */
export function toVisibleChatMessages(raw: ChatMessage[]): ChatMessage[] {
  return raw.filter(
    (m) => (m.role === "user" || m.role === "assistant") && Boolean(m.content?.trim()),
  );
}
