import type { MessageKey } from "@/i18n/catalog";

/** Message keys associated with turn states; used only for type constraints. */
export type TurnLabelKey = Extract<MessageKey<"interview">, `status.turn.${string}`>;

/** Map a turn state to UI copy; unknown states return null for caller fallback. */
export function turnLabelKey(turnState: string): TurnLabelKey | null {
  switch (turnState) {
    case "AI_SPEAKING":
      return "status.turn.aiSpeaking";
    case "USER_SPEAKING":
      return "status.turn.userSpeaking";
    case "PROCESSING":
      return "status.turn.processing";
    case "IDLE":
      return "status.turn.idle";
    default:
      return null;
  }
}
