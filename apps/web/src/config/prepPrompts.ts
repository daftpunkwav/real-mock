/**
 * @file prepPrompts.ts
 * @description Interview prep quick-prompt keys.
 *
 * Keys only; copy lives in `i18n/messages/<locale>/prep.ts`.
 * UI translates with the active locale before filling the input.
 */
import type { MessageKey } from "@/i18n/catalog";

export type PrepQuickPromptKey = Extract<MessageKey<"prep">, `quick.${string}`>;

export const PREP_QUICK_PROMPT_KEYS: readonly PrepQuickPromptKey[] = [
  "quick.analyzeResume",
  "quick.techQuestions",
  "quick.behavioralMock",
  "quick.searchExperiences",
] as const;
