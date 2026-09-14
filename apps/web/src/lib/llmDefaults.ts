/**
 * @file llmDefaults.ts
 * @description Shared LLM token-budget defaults for the web app.
 *
 * Defaults mirror backend capability defaults; update together with backend.
 * User-configured values win; these apply only when a field is empty/unset.
 */

export const DEFAULT_CONTEXT_WINDOW = 256_000;

export const DEFAULT_MAX_OUTPUT_TOKENS = 64_000;
