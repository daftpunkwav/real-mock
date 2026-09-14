/**
 * @file modelChoice.ts
 * @description Selected chat model resolution helper.
 */

import type { ModelProfile } from "@/types";

/** Return the default profile for null id; null when unmatched. */
export function resolveSelectedModel(
  chatModels: ModelProfile[],
  selectedModelId: number | null,
  defaultChatProfile: ModelProfile | null,
): ModelProfile | null {
  if (selectedModelId === null) return defaultChatProfile;
  return chatModels.find((m) => m.id === selectedModelId) ?? null;
}
