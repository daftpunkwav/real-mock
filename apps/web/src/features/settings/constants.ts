/** Settings model options and draft helpers. */

import type { MessageKey } from "@/i18n";
import { DEFAULT_CONTEXT_WINDOW, DEFAULT_MAX_OUTPUT_TOKENS } from "@/lib/llmDefaults";
import type { LLMProtocol, ModelProfile } from "@/types";

/** settings key,Use labelKey/hintKey . */
type SettingsMessageKey = MessageKey<"settings">;

export const PROTOCOL_OPTIONS: { value: LLMProtocol; label: string }[] = [
  // .
  { value: "openai_chat", label: "OpenAI Chat Completions" },
  { value: "anthropic_messages", label: "Anthropic Messages (/v1/messages)" },
  { value: "openai_responses", label: "OpenAI Responses" },
];

export const CAP_OPTIONS: {
  key: keyof ModelProfile["capabilities"];
  labelKey: SettingsMessageKey;
}[] = [
  { key: "chat", labelKey: "caps.chat" },
  { key: "vision", labelKey: "caps.vision" },
  { key: "audio_input", labelKey: "caps.audio_input" },
  { key: "audio_output", labelKey: "caps.audio_output" },
  { key: "reasoning", labelKey: "caps.reasoning" },
];

export const TASK_META: {
  task: "chat" | "stt" | "tts";
  labelKey: SettingsMessageKey;
  hintKey: SettingsMessageKey;
  capKey: keyof ModelProfile["capabilities"];
}[] = [
  { task: "chat", labelKey: "tasks.chat.label", hintKey: "tasks.chat.hint", capKey: "chat" },
  { task: "stt", labelKey: "tasks.stt.label", hintKey: "tasks.stt.hint", capKey: "audio_input" },
  { task: "tts", labelKey: "tasks.tts.label", hintKey: "tasks.tts.hint", capKey: "audio_output" },
];

/** Press , Use */
export function modelsForTask(models: ModelProfile[], capKey: keyof ModelProfile["capabilities"]) {
  return models.filter((m) => m.capabilities?.[capKey]);
}

export function formatWindow(n: number) {
  if (!n) return "—";
  return n >= 1000 ? `${Math.round(n / 1000)}K` : String(n);
}

export interface ModelDraft {
  model: string;
  display_name: string;
  context_window: string;
  max_output: string;
  capabilities: ModelProfile["capabilities"];
  extras_text: string;
}

export const EMPTY_DRAFT: ModelDraft = {
  model: "",
  display_name: "",
  context_window: String(DEFAULT_CONTEXT_WINDOW),
  max_output: String(DEFAULT_MAX_OUTPUT_TOKENS),
  capabilities: { chat: true, vision: false, audio_input: false, audio_output: false, reasoning: false },
  extras_text: "",
};
